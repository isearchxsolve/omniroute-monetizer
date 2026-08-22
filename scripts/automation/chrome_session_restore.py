#!/usr/bin/env python3
"""Restore a Chrome profile's SIGN-IN STATE from a verified local source. Fail-closed.

What this fixes
---------------
The 2026-08-22 incident: four live profiles lost their Chrome Sync credential (see
CHROME_PROFILE_RCA.md and MASTER_WORKLOG.md #1022). `restore_chrome_profiles.ps1` could
restore whole profile trees or repair display labels, but neither is the right unit of
work for this failure:

  * a full tree restore reverts ALL browsing data for ALL four profiles, and
  * a `Local State > info_cache` label repair is transient -- Chrome clears a label that
    has no credential behind it.

The credential is exactly two artifacts, per profile:

    <profile>/Web Data     -> table token_service   (OS-encrypted refresh token)
    <profile>/Preferences  -> key  account_info     (primary-account record)

They must be restored TOGETHER and they must come from the SAME snapshot, or Chrome sees
an account with no token (or a token with no account) and clears both. This script moves
exactly that pair, plus the matching `Local State` display label, for ONE named profile.

What this is NOT
----------------
This does not, and cannot, create or refresh a Google session. It replaces local files
with the operator's own earlier copies of those same files, under the same Windows
account. Nothing is fabricated, injected, decrypted, or bypassed. No SQLite row is
edited. If Google has revoked the token server-side, Chrome will reject it on first
contact and show "Sign in to Chrome" again -- in which case the ONLY remaining path is a
normal Google sign-in, and this script's rollback puts everything back.

Fail-closed preconditions (ALL must pass)
-----------------------------------------
  1. Chrome is not running.
  2. The live root is the canonical root (override needs --i-know-what-im-doing).
  3. Source and live `Local State` have an IDENTICAL os_crypt key fingerprint, so the
     encrypted token will still decrypt on this machine.
  4. The source profile carries a COMPLETE credential: token_service rows > 0 AND
     account_info non-empty.
  5. The source account email matches the expected account for that profile, so a
     credential cannot be restored into the wrong person's profile.
  6. Every file about to be overwritten is copied to a timestamped rollback directory
     first, and is restored automatically if any step raises.

Usage
-----
    # 1. see what would happen (default; changes nothing)
    python chrome_session_restore.py --profile "Profile 17" \
        --source "D:\\omniroute-backups\\chrome-profiles\\chrome_profile_20260822_080520"

    # 2. do it
    python chrome_session_restore.py --profile "Profile 17" \
        --source "D:\\omniroute-backups\\chrome-profiles\\chrome_profile_20260822_080520" --confirm

    # 3. undo it
    python chrome_session_restore.py --rollback <rollback-dir-printed-in-step-2>

Then OPEN CHROME AND LOOK AT THE PROFILE MENU. Nothing here may be reported as
GOOGLE_SYNC_AUTHENTICATED until that menu stops saying "Sign in to Chrome".
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
import time

CANONICAL_ROOT = os.path.join(
    os.environ.get("LOCALAPPDATA", r"C:\Users\Admin\AppData\Local"),
    "Google", "Chrome", "User Data",
)
ROLLBACK_ROOT = r"D:\omniroute-backups\chrome-session-rollback"

EXPECTED_ACCOUNTS = {
    "Default": "kunal.colab@gmail.com",
    "Profile 14": "xxpertcomments@gmail.com",
    "Profile 16": "niloydassana@gmail.com",
    "Profile 17": "isearch.xsolve@gmail.com",
}

# The credential pair. Order matters only for reporting.
CREDENTIAL_FILES = ["Web Data", "Preferences"]


class PreconditionFailed(Exception):
    """Raised when a fail-closed gate trips. Nothing has been modified."""


# --------------------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(msg, flush=True)


def chrome_is_running() -> bool:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return True  # fail closed
    return "chrome.exe" in out.lower()


def read_json(path: str):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return json.load(fh)


def write_json_atomic(path: str, obj) -> None:
    """Write UTF-8 without BOM (Chrome will not parse a BOM), via a temp file + replace."""
    tmp = path + ".tmp_restore"
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(data)
    os.replace(tmp, path)


def oscrypt_fingerprint(local_state_path: str) -> str | None:
    try:
        key = read_json(local_state_path).get("os_crypt", {}).get("encrypted_key")
    except Exception:
        return None
    return hashlib.sha256(base64.b64decode(key)).hexdigest() if key else None


def token_service_rows(web_data_path: str) -> int:
    """Count rows only. The encrypted token value is never read."""
    tmpd = tempfile.mkdtemp(prefix="chrome_tok_")
    try:
        dst = os.path.join(tmpd, "wd.db")
        shutil.copy2(web_data_path, dst)
        con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='token_service'")
            if not cur.fetchone():
                return 0
            cur.execute("SELECT COUNT(*) FROM token_service")
            return cur.fetchone()[0]
        finally:
            con.close()
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)


def account_emails(preferences_path: str) -> list[str]:
    try:
        ai = read_json(preferences_path).get("account_info") or []
    except Exception:
        return []
    return [a.get("email") for a in ai if a.get("email")]


# ------------------------------------------------------------------------ validation

def validate(live_root: str, source_root: str, profile: str, force_root: bool) -> dict:
    log("-- preconditions " + "-" * 60)

    if chrome_is_running():
        raise PreconditionFailed(
            "Chrome is running. Close every Chrome window (and confirm no chrome.exe "
            "remains in Task Manager) before any profile file is touched."
        )
    log("   [ok] Chrome is not running")

    same = (os.path.normcase(os.path.abspath(live_root).rstrip("\\"))
            == os.path.normcase(CANONICAL_ROOT.rstrip("\\")))
    if not same and not force_root:
        raise PreconditionFailed(
            f"Live root {live_root!r} is not the canonical root {CANONICAL_ROOT!r}. "
            "Writing to a non-canonical root is how the original incident happened. "
            "Pass --i-know-what-im-doing only for an isolated test tree."
        )
    log(f"   [{'ok' if same else 'OVERRIDDEN'}] live root = {live_root}")

    live_ls = os.path.join(live_root, "Local State")
    src_ls = os.path.join(source_root, "Local State")
    for p in (live_ls, src_ls):
        if not os.path.exists(p):
            raise PreconditionFailed(f"Missing Local State: {p}")

    lfp, sfp = oscrypt_fingerprint(live_ls), oscrypt_fingerprint(src_ls)
    if not lfp or not sfp:
        raise PreconditionFailed("Could not read an os_crypt encryption key from Local State.")
    if lfp != sfp:
        raise PreconditionFailed(
            "Chrome encryption key MISMATCH between source and live.\n"
            f"    live   {lfp[:32]}\n    source {sfp[:32]}\n"
            "The source is from a different Windows account or Chrome install, so its "
            "encrypted token could never decrypt here. Refusing."
        )
    log(f"   [ok] os_crypt key fingerprint matches ({lfp[:32]})")

    src_prof = os.path.join(source_root, profile)
    live_prof = os.path.join(live_root, profile)
    if not os.path.isdir(src_prof):
        raise PreconditionFailed(f"Source profile directory not found: {src_prof}")
    if not os.path.isdir(live_prof):
        raise PreconditionFailed(f"Live profile directory not found: {live_prof}")

    missing = [f for f in CREDENTIAL_FILES if not os.path.exists(os.path.join(src_prof, f))]
    if missing:
        raise PreconditionFailed(
            f"Source {profile!r} is missing {missing}. Both halves of the credential "
            "must come from the same snapshot."
        )

    rows = token_service_rows(os.path.join(src_prof, "Web Data"))
    emails = account_emails(os.path.join(src_prof, "Preferences"))
    if rows == 0:
        raise PreconditionFailed(
            f"Source {profile!r} has 0 token_service rows -- no Sync credential to restore. "
            "This profile can only be recovered by a normal Google sign-in."
        )
    if not emails:
        raise PreconditionFailed(
            f"Source {profile!r} has an empty Preferences>account_info -- the token would "
            "be orphaned and Chrome would clear it. Refusing."
        )
    log(f"   [ok] source credential is complete: token_service rows={rows}, account={emails}")

    expected = EXPECTED_ACCOUNTS.get(profile)
    if expected and expected not in emails:
        raise PreconditionFailed(
            f"ACCOUNT MISMATCH for {profile!r}: expected {expected}, source holds {emails}. "
            "Restoring this would sign the profile in as the wrong account. Refusing."
        )
    log(f"   [ok] account matches expected owner of {profile!r}")

    return {"live_profile": live_prof, "source_profile": src_prof,
            "token_rows": rows, "emails": emails,
            "live_local_state": live_ls, "source_local_state": src_ls}


# --------------------------------------------------------------------------- actions

def do_restore(ctx: dict, profile: str, dry_run: bool) -> str | None:
    live_prof, src_prof = ctx["live_profile"], ctx["source_profile"]
    live_ls, src_ls = ctx["live_local_state"], ctx["source_local_state"]

    planned = [(os.path.join(src_prof, f), os.path.join(live_prof, f))
               for f in CREDENTIAL_FILES]

    log("\n-- plan " + "-" * 69)
    for s, d in planned:
        log(f"   copy  {s}\n     ->  {d}")
    log(f"   merge Local State > profile.info_cache[{profile!r}] from the same source")

    if dry_run:
        log("\nDRY RUN -- nothing was changed. Re-run with --confirm to apply.")
        return None

    stamp = time.strftime("%Y%m%d_%H%M%S")
    rb = os.path.join(ROLLBACK_ROOT, f"{profile.replace(' ', '_')}_{stamp}")
    os.makedirs(rb, exist_ok=True)

    # ---- back up EVERY file we are about to touch, before touching any of them
    manifest = {"created": stamp, "profile": profile, "live_root": os.path.dirname(live_prof),
                "source": os.path.dirname(src_prof), "files": []}
    for _, dest in planned:
        if os.path.exists(dest):
            shutil.copy2(dest, os.path.join(rb, os.path.basename(dest)))
            manifest["files"].append({"restored_to": dest,
                                      "backup": os.path.basename(dest)})
    shutil.copy2(live_ls, os.path.join(rb, "Local State"))
    manifest["files"].append({"restored_to": live_ls, "backup": "Local State"})
    write_json_atomic(os.path.join(rb, "rollback.json"), manifest)
    log(f"\n   rollback point: {rb}")

    try:
        for s, d in planned:
            shutil.copy2(s, d)
            log(f"   [done] {os.path.basename(d)}")

        # Merge ONLY this profile's info_cache entry; leave every other profile alone.
        live_state = read_json(live_ls)
        src_entry = (read_json(src_ls).get("profile", {})
                     .get("info_cache", {}).get(profile))
        if src_entry:
            live_state.setdefault("profile", {}).setdefault("info_cache", {})[profile] = src_entry
            write_json_atomic(live_ls, live_state)
            log(f"   [done] Local State info_cache[{profile!r}] "
                f"-> {src_entry.get('user_name') or '(no email)'}")
        else:
            log("   [skip] source has no info_cache entry for this profile")
    except Exception as exc:
        log(f"\n!! FAILED: {exc}\n!! rolling back automatically...")
        rollback(rb)
        raise

    log("\n" + "=" * 74)
    log("FILES RESTORED. THIS IS NOT YET A VERIFIED FIX.")
    log("=" * 74)
    log("  1. Open Chrome and switch to this profile.")
    log("  2. Open the profile menu (avatar, top-right).")
    log("  3. If it still says \"Sign in to Chrome\", Google has revoked the token. The")
    log("     only remaining path is a normal sign-in. Undo with:")
    log(f"         python {os.path.basename(__file__)} --rollback \"{rb}\"")
    log("  4. Only if the account is shown may this be recorded as")
    log("     GOOGLE_SYNC_AUTHENTICATED. Log the outcome in MASTER_WORKLOG.md either way.")
    return rb


def rollback(rb_dir: str) -> int:
    mpath = os.path.join(rb_dir, "rollback.json")
    if not os.path.exists(mpath):
        log(f"FATAL: no rollback.json in {rb_dir}")
        return 2
    if chrome_is_running():
        log("FATAL: Chrome is running. Close it before rolling back.")
        return 1
    m = read_json(mpath)
    log(f"-- rolling back {m['profile']!r} (captured {m['created']})")
    for f in m["files"]:
        src = os.path.join(rb_dir, f["backup"])
        if not os.path.exists(src):
            log(f"   [warn] missing backup {src}")
            continue
        shutil.copy2(src, f["restored_to"])
        log(f"   [done] {f['restored_to']}")
    log("Rollback complete. The profile is back to its pre-restore state.")
    return 0


# ------------------------------------------------------------------------------ main

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Restore one Chrome profile's sign-in credential from a verified "
                    "local source. Dry-run unless --confirm is passed.")
    ap.add_argument("--profile", help='e.g. "Profile 17"')
    ap.add_argument("--source", help="snapshot root containing <profile>/Web Data")
    ap.add_argument("--live-root", default=CANONICAL_ROOT)
    ap.add_argument("--confirm", action="store_true", help="actually apply the change")
    ap.add_argument("--rollback", metavar="DIR", help="undo a previous restore")
    ap.add_argument("--i-know-what-im-doing", action="store_true",
                    dest="force_root", help="permit a non-canonical live root")
    args = ap.parse_args()

    if args.rollback:
        return rollback(args.rollback)
    if not args.profile or not args.source:
        ap.error("--profile and --source are required (or use --rollback)")

    log("=" * 74)
    log("CHROME SIGN-IN CREDENTIAL RESTORE")
    log("=" * 74)
    log(f"profile : {args.profile}")
    log(f"source  : {args.source}")
    log(f"live    : {args.live_root}")
    log(f"mode    : {'APPLY' if args.confirm else 'DRY RUN'}\n")

    try:
        ctx = validate(args.live_root, args.source, args.profile, args.force_root)
    except PreconditionFailed as exc:
        log(f"\nREFUSED (nothing was modified):\n  {exc}")
        return 1

    try:
        do_restore(ctx, args.profile, dry_run=not args.confirm)
    except Exception as exc:
        log(f"\nERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
