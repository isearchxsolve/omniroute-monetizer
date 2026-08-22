#!/usr/bin/env python3
"""Chrome profile / authentication state auditor  (STRICTLY READ-ONLY).

Why this exists
---------------
The 2026-08-22 incident (see CHROME_PROFILE_RCA.md, MASTER_WORKLOG.md #1013-#1022) was
prolonged because every health check used the WRONG SIGNALS:

  * "Cookies file is 2,195,456 bytes, so the profile is intact."
    WRONG. SQLite never reclaims pages on DELETE. That file was 98.1% free pages holding
    72 rows. File size preserves the high-water mark of data that is already GONE.

  * "Local State > profile.info_cache shows the account email, so we are signed in."
    WRONG. That field is a display label. Chrome reconciles it against
    Preferences > account_info at startup and CLEARS it when no credential backs it.
    Repairing it is transient by design.

  * "Google cookies are present, so Chrome Sync is authenticated."
    WRONG. Website cookies are unrelated to the Sync credential. Also: the auth cookies
    on this machine live on `.google.co.in` / `.youtube.com`, so a query narrowed to
    `%.google.com` reports a false negative.

The Chrome Sync credential is an OS-encrypted refresh token in
`<profile>/Web Data` -> table `token_service`, paired with a primary-account record in
`<profile>/Preferences` -> `account_info`. NEITHER was ever checked before #1022.
Checking them found a real, untried recovery source for 3 of 4 profiles.

This script checks the signals that actually matter and fails closed.

Guarantees
----------
* Opens nothing in the live tree for write. SQLite files are copied to a temp dir and
  opened `mode=ro`, then the copy is deleted.
* Never reads, decrypts, or prints a token value, a cookie value, or a password.
  Only presence, row counts, blob LENGTHS, and email labels.
* Gaia account ids are truncated to the last 4 digits.

Usage
-----
    python chrome_auth_audit.py                       # audit live root + scan all sources
    python chrome_auth_audit.py --json report.json    # machine-readable report
    python chrome_auth_audit.py --gate                # exit 1 unless all 4 are authenticated

Exit codes
----------
    0  every required profile is GOOGLE_SYNC_AUTHENTICATED  (only with --gate)
    1  at least one required profile is NOT authenticated, or a fail-closed check tripped
    2  usage / environment error
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

CANONICAL_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Admin\AppData\Local"),
    "Google", "Chrome", "User Data",
)

REQUIRED_PROFILES = ["Default", "Profile 14", "Profile 16", "Profile 17"]

EXPECTED_ACCOUNTS = {
    "Default": "kunal.colab@gmail.com",
    "Profile 14": "xxpertcomments@gmail.com",
    "Profile 16": "niloydassana@gmail.com",
    "Profile 17": "isearch.xsolve@gmail.com",
}

# Historical roots that may hold a recoverable session. Read-only sources only.
CANDIDATE_SOURCE_ROOTS = [
    r"D:\omniroute-backups\chrome-profiles",          # expanded: each snapshot subdir
    r"D:\omniroute-chrome-profile-v2",
    r"D:\omniroute-chrome-profile",
    r"D:\omniroute-pure-chrome",
    r"D:\omniroute-monetizer\state\harvest_profile",
    r"D:\omniroute-monetizer\state\_orphan_live_link_scaffold_20260822",
]

# Aliases that automation has historically abused. A PLAIN DIRECTORY here is a red alert:
# that is exactly how Chrome got pointed at a fresh empty scaffold (RCA root cause R1).
KNOWN_ALIASES = [r"D:\omniroute-monetizer\state\live_link"]

GOOGLE_AUTH_COOKIE_NAMES = (
    "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PSIDTS",
    "SID", "HSID", "SSID", "SAPISID", "APISID", "LSID",
)


# --------------------------------------------------------------------------- helpers

def chrome_is_running() -> bool:
    """True if any chrome.exe is live. File operations MUST NOT proceed if so."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return True  # fail closed: if we cannot tell, assume it is running
    return "chrome.exe" in out.lower()


def read_json(path: str):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return json.load(fh)


def oscrypt_fingerprint(local_state_path: str) -> str | None:
    """SHA-256 of the DPAPI-protected Chrome master key. Equality => same encryption
    lineage, i.e. a copied profile's encrypted blobs will still decrypt here."""
    try:
        key = read_json(local_state_path).get("os_crypt", {}).get("encrypted_key")
    except Exception:
        return None
    if not key:
        return None
    return hashlib.sha256(base64.b64decode(key)).hexdigest()


def cookies_path(profile_dir: str) -> str | None:
    for rel in (os.path.join("Network", "Cookies"), "Cookies"):
        p = os.path.join(profile_dir, rel)
        if os.path.exists(p):
            return p
    return None


def sqlite_probe(db_path: str, fn):
    """Copy a possibly-locked SQLite db to temp, open read-only, run fn(cursor)."""
    tmpd = tempfile.mkdtemp(prefix="chrome_audit_")
    try:
        dst = os.path.join(tmpd, "probe.db")
        shutil.copy2(db_path, dst)
        con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
        try:
            return fn(con.cursor())
        finally:
            con.close()
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def table_exists(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


# ------------------------------------------------------------------ per-profile probe

def probe_profile(root: str, profile: str) -> dict:
    """Collect every signal that actually distinguishes the four auth states."""
    d = os.path.join(root, profile)
    r: dict = {"profile": profile, "exists": os.path.isdir(d)}
    if not r["exists"]:
        return r

    # --- 1. Sync credential: Web Data -> token_service  (THE authoritative signal)
    wd = os.path.join(d, "Web Data")
    r["web_data_present"] = os.path.exists(wd)
    r["token_service_rows"] = None
    r["token_accounts"] = []
    if r["web_data_present"]:
        def _tok(cur):
            if not table_exists(cur, "token_service"):
                return None, []
            cur.execute("SELECT service, LENGTH(encrypted_token) FROM token_service")
            rows = cur.fetchall()
            # Truncate the gaia id; record blob length only. Never the value.
            return len(rows), [
                {"account": f"...{str(s).strip()[-4:]}", "blob_len": ln} for s, ln in rows
            ]
        try:
            r["token_service_rows"], r["token_accounts"] = sqlite_probe(wd, _tok)
        except Exception as exc:
            r["token_service_error"] = str(exc)

    # --- 2. Primary-account record: Preferences -> account_info
    prefs = os.path.join(d, "Preferences")
    r["preferences_present"] = os.path.exists(prefs)
    r["account_info_count"] = None
    r["account_emails"] = []
    if r["preferences_present"]:
        try:
            p = read_json(prefs)
            ai = p.get("account_info") or []
            r["account_info_count"] = len(ai)
            r["account_emails"] = [a.get("email") for a in ai if a.get("email")]
            svc = (p.get("google") or {}).get("services") or {}
            r["consented_to_sync"] = svc.get("consented_to_sync")
            lg = svc.get("last_gaia_id")
            r["last_gaia_id"] = f"...{str(lg)[-4:]}" if lg else None
            r["sync_requested"] = (p.get("sync") or {}).get("requested")
        except Exception as exc:
            r["preferences_error"] = str(exc)

    # --- 3. Display label only: Local State -> profile.info_cache
    ls = os.path.join(root, "Local State")
    if os.path.exists(ls):
        try:
            ic = read_json(ls).get("profile", {}).get("info_cache", {}).get(profile) or {}
            r["info_cache_name"] = ic.get("name")
            r["info_cache_user_name"] = ic.get("user_name") or ""
            r["info_cache_has_gaia"] = bool(ic.get("gaia_id"))
        except Exception as exc:
            r["local_state_error"] = str(exc)

    # --- 4. Cookie store health: ROWS + FREELIST, never file size
    ck = cookies_path(d)
    r["cookies_present"] = ck is not None
    if ck:
        r["cookies_file_bytes"] = os.path.getsize(ck)

        def _ck(cur):
            cur.execute("SELECT COUNT(*) FROM cookies")
            rows = cur.fetchone()[0]
            cur.execute("PRAGMA page_count"); pc = cur.fetchone()[0]
            cur.execute("PRAGMA freelist_count"); fl = cur.fetchone()[0]
            q = ",".join("?" * len(GOOGLE_AUTH_COOKIE_NAMES))
            # Host-agnostic: auth cookies may sit on .google.co.in / .youtube.com etc.
            cur.execute(f"SELECT COUNT(*) FROM cookies WHERE name IN ({q})",
                        GOOGLE_AUTH_COOKIE_NAMES)
            auth = cur.fetchone()[0]
            cur.execute("SELECT COUNT(DISTINCT host_key) FROM cookies")
            hosts = cur.fetchone()[0]
            return rows, pc, fl, auth, hosts
        try:
            rows, pc, fl, auth, hosts = sqlite_probe(ck, _ck)
            r["cookie_rows"] = rows
            r["cookie_pages"] = pc
            r["cookie_free_pages"] = fl
            r["cookie_pct_free"] = round(100.0 * fl / pc, 1) if pc else None
            r["google_auth_cookie_rows"] = auth
            r["cookie_distinct_hosts"] = hosts
            # The signature that burned us: big file, almost no rows, mostly free pages.
            r["cookie_store_purged"] = bool(pc >= 40 and r["cookie_pct_free"] and
                                            r["cookie_pct_free"] >= 60.0 and rows < 500)
        except Exception as exc:
            r["cookies_error"] = str(exc)

    # --- 5. Is this a real, long-used profile or a fresh scaffold?
    hist = os.path.join(d, "History")
    if os.path.exists(hist):
        def _h(cur):
            cur.execute("SELECT COUNT(*) FROM urls"); u = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM visits"); v = cur.fetchone()[0]
            return u, v
        try:
            r["history_urls"], r["history_visits"] = sqlite_probe(hist, _h)
        except Exception as exc:
            r["history_error"] = str(exc)

    # --- 6. Classify. GOOGLE_SYNC_AUTHENTICATED needs BOTH halves of the credential.
    labels = []
    if r["exists"]:
        labels.append("LOCAL_DATA_PRESENT")
    if r.get("info_cache_user_name"):
        labels.append("PROFILE_METADATA_REGISTERED")
    has_tok = bool(r.get("token_service_rows"))
    has_acct = bool(r.get("account_info_count"))
    if has_tok and has_acct:
        labels.append("GOOGLE_SYNC_CREDENTIAL_ON_DISK")
    r["status_labels"] = labels
    r["sync_credential_complete"] = has_tok and has_acct
    # Deliberately NOT asserting GOOGLE_SYNC_AUTHENTICATED: that requires Chrome's UI to
    # stop showing "Sign in to Chrome". On-disk material can only ever be a precondition.
    return r


def probe_root(root: str, profiles=None) -> dict:
    profiles = profiles or REQUIRED_PROFILES
    ls = os.path.join(root, "Local State")
    fp = oscrypt_fingerprint(ls) if os.path.exists(ls) else None
    return {
        "root": root,
        "exists": os.path.isdir(root),
        "local_state_present": os.path.exists(ls),
        "oscrypt_fingerprint": (fp[:32] if fp else None),
        "profiles": [probe_profile(root, p) for p in profiles],
    }


def classify_alias(alias: str, expected_target: str) -> dict:
    """A plain directory at an alias path is the RCA's primary root cause. Fail closed."""
    out = {"alias": alias, "exists": os.path.exists(alias)}
    if not out["exists"]:
        out["verdict"] = "ABSENT_OK"
        return out
    try:
        real = os.path.realpath(alias)
    except Exception as exc:
        out["verdict"] = "UNRESOLVABLE"
        out["error"] = str(exc)
        return out
    out["resolves_to"] = real
    is_link = os.path.islink(alias) or (
        os.path.normcase(real) != os.path.normcase(os.path.abspath(alias))
    )
    if not is_link:
        out["verdict"] = "PLAIN_DIRECTORY_DANGER"
    elif os.path.normcase(real.rstrip("\\")) == os.path.normcase(expected_target.rstrip("\\")):
        out["verdict"] = "JUNCTION_OK"
    else:
        out["verdict"] = "JUNCTION_WRONG_TARGET"
    return out


def enumerate_source_roots() -> list[str]:
    roots: list[str] = []
    for r in CANDIDATE_SOURCE_ROOTS:
        if not os.path.isdir(r):
            continue
        # A backup parent holds timestamped snapshot subdirectories.
        subs = [os.path.join(r, d) for d in sorted(os.listdir(r))
                if os.path.isdir(os.path.join(r, d))]
        if any(os.path.exists(os.path.join(s, "Local State")) for s in subs):
            roots.extend(s for s in subs if os.path.exists(os.path.join(s, "Local State")))
        else:
            roots.append(r)
    return roots


# ------------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only Chrome auth-state auditor.")
    ap.add_argument("--live-root", default=CANONICAL_ROOT)
    ap.add_argument("--json", metavar="PATH", help="write the full report as JSON")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 unless every required profile has a complete on-disk "
                         "Sync credential (for use as an automation preflight)")
    ap.add_argument("--skip-sources", action="store_true",
                    help="audit the live root only; skip the recovery coverage map")
    args = ap.parse_args()

    live_root = args.live_root
    report: dict = {
        "canonical_root": CANONICAL_ROOT,
        "audited_root": live_root,
        "root_is_canonical": os.path.normcase(os.path.abspath(live_root).rstrip("\\"))
                             == os.path.normcase(CANONICAL_ROOT.rstrip("\\")),
        "chrome_running": chrome_is_running(),
        "aliases": [classify_alias(a, CANONICAL_ROOT) for a in KNOWN_ALIASES],
    }

    print("=" * 78)
    print("CHROME AUTH-STATE AUDIT  (read-only; no token or cookie value is read)")
    print("=" * 78)
    print(f"canonical root : {CANONICAL_ROOT}")
    print(f"audited root   : {live_root}")
    print(f"root canonical : {'YES' if report['root_is_canonical'] else 'NO  <-- REFUSE TO PROCEED'}")
    print(f"chrome running : {'YES  <-- close Chrome before ANY file operation' if report['chrome_running'] else 'no'}")

    print("\n-- alias / junction safety " + "-" * 51)
    for a in report["aliases"]:
        print(f"   {a['alias']}")
        print(f"     verdict: {a['verdict']}"
              + (f"  -> {a.get('resolves_to')}" if a.get("resolves_to") else ""))
        if a["verdict"] == "PLAIN_DIRECTORY_DANGER":
            print("     *** A PLAIN DIRECTORY HERE IS THE RCA ROOT CAUSE (R1). Chrome will")
            print("     *** scaffold empty profiles into it. Automation MUST abort.")

    if not os.path.isdir(live_root):
        print(f"\nFATAL: live root does not exist: {live_root}")
        return 2

    live = probe_root(live_root)
    report["live"] = live
    print(f"\n-- live profiles " + "-" * 61)
    print(f"   os_crypt key sha256[:32] = {live['oscrypt_fingerprint']}")
    for p in live["profiles"]:
        if not p["exists"]:
            print(f"   {p['profile']:11} MISSING")
            continue
        print(f"   {p['profile']:11} label={str(p.get('info_cache_name')):12} "
              f"registered_email={p.get('info_cache_user_name') or '(blank)'}")
        print(f"               token_service_rows={p.get('token_service_rows')}  "
              f"account_info={p.get('account_info_count')} {p.get('account_emails') or ''}  "
              f"credential_complete={p.get('sync_credential_complete')}")
        print(f"               cookies rows={p.get('cookie_rows')} "
              f"({p.get('cookie_pct_free')}% free pages, {p.get('cookie_file_bytes') or p.get('cookies_file_bytes')}B) "
              f"google_auth_cookies={p.get('google_auth_cookie_rows')}"
              + ("   <-- STORE PURGED" if p.get("cookie_store_purged") else ""))
        print(f"               history urls={p.get('history_urls')} visits={p.get('history_visits')}")
        exp = EXPECTED_ACCOUNTS.get(p["profile"])
        if exp and p.get("account_emails") and exp not in p["account_emails"]:
            print(f"               NOTE expected {exp}, on-disk {p['account_emails']}")

    unauth = [p["profile"] for p in live["profiles"]
              if not p.get("sync_credential_complete")]
    report["profiles_without_credential"] = unauth

    # ---------------- recovery coverage map
    if not args.skip_sources:
        print(f"\n-- recovery coverage map (which source can restore which profile) " + "-" * 12)
        coverage: dict[str, list[dict]] = {p: [] for p in REQUIRED_PROFILES}
        sources = []
        for sroot in enumerate_source_roots():
            if os.path.normcase(os.path.abspath(sroot)) == os.path.normcase(os.path.abspath(live_root)):
                continue
            sr = probe_root(sroot)
            sources.append(sr)
            same_key = (sr["oscrypt_fingerprint"] and live["oscrypt_fingerprint"]
                        and sr["oscrypt_fingerprint"] == live["oscrypt_fingerprint"])
            for p in sr["profiles"]:
                if p.get("sync_credential_complete"):
                    expected = EXPECTED_ACCOUNTS.get(p["profile"])
                    emails = p.get("account_emails") or []
                    # A credential in the right FOLDER can still be the WRONG ACCOUNT.
                    # e.g. harvest_profile\Default holds Profile 14's account. Restoring
                    # that into Default would sign it in as the wrong person.
                    mismatch = bool(expected and emails and expected not in emails)
                    coverage[p["profile"]].append({
                        "source": sroot,
                        "emails": emails,
                        "same_encryption_key": bool(same_key),
                        "account_mismatch": mismatch,
                        "usable": bool(same_key) and not mismatch,
                    })
        report["sources"] = sources
        report["coverage"] = coverage
        for prof in REQUIRED_PROFILES:
            hits = coverage[prof]
            usable = [h for h in hits if h["usable"]]
            if not usable:
                print(f"   {prof:11} NO USABLE LOCAL SOURCE -- requires a normal Google sign-in")
            for h in hits:
                if h["usable"]:
                    flag = "USABLE (same-key, account matches)"
                elif h["account_mismatch"]:
                    flag = (f"REJECT: WRONG ACCOUNT (expected "
                            f"{EXPECTED_ACCOUNTS.get(prof)})")
                else:
                    flag = "REJECT: different encryption key"
                print(f"   {prof:11} <- {h['source']}")
                print(f"   {'':11}    {h['emails']}  [{flag}]")

    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    if unauth:
        print(f"  NOT authenticated (no complete on-disk credential): {', '.join(unauth)}")
    else:
        print("  every required profile has a complete on-disk Sync credential")
    print("  REMINDER: an on-disk credential is a PRECONDITION, not proof. Do not report")
    print("  GOOGLE_SYNC_AUTHENTICATED until Chrome's profile menu stops showing")
    print("  \"Sign in to Chrome\" for that profile.")

    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"\n  JSON report written to {args.json}")

    if args.gate:
        if report["chrome_running"]:
            print("\n  GATE FAIL: Chrome is running.")
            return 1
        if not report["root_is_canonical"]:
            print("\n  GATE FAIL: audited root is not the canonical root.")
            return 1
        if any(a["verdict"] in ("PLAIN_DIRECTORY_DANGER", "JUNCTION_WRONG_TARGET")
               for a in report["aliases"]):
            print("\n  GATE FAIL: an alias path is unsafe.")
            return 1
        if unauth:
            print("\n  GATE FAIL: missing credential for: " + ", ".join(unauth))
            return 1
        print("\n  GATE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
