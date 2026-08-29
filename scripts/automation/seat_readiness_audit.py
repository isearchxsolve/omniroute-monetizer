#!/usr/bin/env python3
"""Which seats are actually ready to sweep, and which sites is each one signed in to.

STRICTLY READ-ONLY. Never reads, decrypts or prints a cookie VALUE -- a cookie value is a bearer
token. Only host names, cookie NAMES, counts and expiry class leave this script.

Why this is not `video_seat.py --jar`
------------------------------------
`_jar()` in video_seat.py answers a narrower question: it hardcodes SUBPROFILE ("Default") and looks
for google + rtst names only. Two problems for a sweep:

  * seat `niloy` runs on `--profile-directory "Profile 17"`, not Default. A Default-only jar read
    reports that seat as empty when it is the one seat with a real Flow project.
  * the sweep targets ~50 chat providers plus the video generators. "Is google signed in" says
    nothing about whether poe.com or huggingface.co would answer.

So this walks every seat in state/video_accounts.json at its OWN subprofile, and scores every target
site independently.

What counts as signed in
------------------------
Presence of cookies on a host proves the site was *visited*, nothing more. A sign-in is claimed only
when the jar holds a cookie whose NAME is auth-shaped (session/token/sid/jwt/next-auth/__Secure-*).
That is still a heuristic -- it can be stale or expired server-side, which no local read can see --
so the verdict is `signed_in_probable`, never `signed_in`. Anything weaker is reported as `visited`.

Expiry is read and compared to now: a jar full of auth cookies that all expired last month is
reported `expired`, not ready. That distinction is the whole point of running this before a sweep.

Usage
-----
    python seat_readiness_audit.py                  # table + state/seat_readiness.json
    python seat_readiness_audit.py --all-hosts      # also dump every host in each jar
    python seat_readiness_audit.py --seat niloy     # one seat
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import sqlite3
import tempfile
import time
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE = ROOT / "state"
PROFILES = STATE / "automation_profiles"
ACCOUNTS = STATE / "video_accounts.json"
SITES = STATE / "free_llm_chat_sites.json"
OUT = STATE / "seat_readiness.json"

# Chrome stores time as microseconds since 1601-01-01. expires_utc == 0 means a session cookie:
# it dies with the browser, so it can never carry a sweep that outlives the window.
CHROME_EPOCH = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)

# Auth-shaped cookie NAMES. Matched case-insensitively as substrings, because every framework spells
# it differently: next-auth.session-token (Flow), connect.sid (express), sessionid (django),
# _session (rails), __Secure-1PSID (google). csrf/xsrf are deliberately NOT here -- a CSRF token is
# handed to anonymous visitors too, so treating it as auth manufactures false readiness.
AUTH_NAME_HINTS = ("session", "sess", "token", "auth", "sid", "jwt", "login", "logged",
                   "credential", "identity", "remember", "__secure-", "__host-", "access")

# The video generators are seat-defining but absent from the chat-site directory.
VIDEO_TARGETS = [
    {"name": "Google Flow (labs.google)", "url": "https://labs.google/fx/tools/flow",
     "category": "Video generators"},
    {"name": "rtst.ai", "url": "https://rtst.ai/", "category": "Video generators"},
    {"name": "digen.ai", "url": "https://digen.ai/", "category": "Video generators"},
    {"name": "veoaifree", "url": "https://veoaifree.com/", "category": "Video generators"},
    # Discovered as open tabs on 2026-08-29 (harness_all_tabs.py).  Chat providers
    # increasingly carry video models too, so these are recorded as video-capable
    # seats; graduation into the CHAT pool still requires a chat-surface capture.
    {"name": "HeyGen Video", "url": "https://app.heygen.com", "category": "Video generators"},
    {"name": "MagicHour Video", "url": "https://magichour.ai", "category": "Video generators"},
    {"name": "Akool Video", "url": "https://www.akool.com", "category": "Video generators"},
    {"name": "NemoVideo", "url": "https://www.nemovideo.com", "category": "Video generators"},
]

# connect_over_cdp attaches to EVERY target before it returns, so the ceiling scales with tab count,
# not with how much work we then do. Measured: seats 9223/9224/9225 connect in about a second, while
# the `providers` seat on 9222 was holding 69 targets (the chat-harvest tabs) and blew a 15s ceiling.
# 90s is sized for that seat. A seat that cannot answer in 90s is reported, never force-recovered.
CDP_TIMEOUT_MS = 90_000


def host_of(url: str) -> str:
    h = url.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return h.lower().lstrip(".")


def registrable(host: str) -> str:
    """Crude eTLD+1. Good enough to group `chat.lmsys.org` with `lmsys.org`; deliberately keeps
    two labels for the common multi-part suffixes so `google.co.in` does not collapse to `co.in`."""
    parts = host.lstrip(".").split(".")
    if len(parts) <= 2:
        return host.lstrip(".")
    if parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) <= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def chrome_time(us: int) -> dt.datetime | None:
    if not us:
        return None
    try:
        return CHROME_EPOCH + dt.timedelta(microseconds=int(us))
    except (OverflowError, ValueError):
        return None


def read_jar_sqlite(cookie_db: pathlib.Path) -> tuple[list[tuple[str, str, int]], str | None]:
    """(host_key, name, expires_unix) from the on-disk jar. 0 == session cookie.

    Only works when the seat's Chrome is CLOSED. On Windows a running Chrome holds Cookies with an
    exclusive lock, which defeats both a copy (PermissionError) and a direct `mode=ro&immutable=1`
    open (OperationalError: unable to open database file). Both were measured failing on all four
    seats, so this is the fallback and CDP is the primary.

    Values are never selected.
    """
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="seatjar_"))
    try:
        dst = tmpdir / "Cookies"
        shutil.copy2(cookie_db, dst)
        for suffix in ("-wal", "-shm", "-journal"):
            sib = cookie_db.with_name(cookie_db.name + suffix)
            if sib.exists():
                shutil.copy2(sib, dst.with_name(dst.name + suffix))
        con = sqlite3.connect(f"file:{dst}?mode=ro", uri=True)
        try:
            rows = con.execute("SELECT host_key, name, expires_utc FROM cookies").fetchall()
        finally:
            con.close()
        out = []
        for h, n, e in rows:
            t = chrome_time(int(e or 0))
            out.append((str(h), str(n), int(t.timestamp()) if t else 0))
        return out, None
    except Exception as e:                                   # fail closed, never guess
        return [], f"{type(e).__name__}: {str(e)[:120]}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def read_jar_cdp_raw(port: int) -> tuple[list[tuple[str, str, int]], str | None]:
    """(domain, name, expires_unix) via one raw CDP `Storage.getCookies`. 0 == session cookie.

    Preferred over the playwright path for two reasons, both measured on the `providers` seat:

      * connect_over_cdp attaches to every target before returning. That seat holds 69 (the chat
        harvest tabs) and it timed out at 15s AND at 90s, stuck on "retrieving websocket url" -- a
        step plain curl completes instantly. This does one websocket round trip and touches no tab.
      * attaching to 69 live provider tabs mid-harvest is a side effect worth not having. Reading a
        browser-level domain cannot disturb a page.

    `suppress_origin` matters: Chrome's DevTools endpoint rejects a handshake that carries an Origin
    header, and websocket-client sends one by default.

    Cookie values arrive in the payload, are never bound to a name here, and are dropped with the
    response object -- only domain, name and expiry integer are returned.
    """
    try:
        import websocket                                      # websocket-client
    except ImportError:
        return [], "websocket-client not installed"
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=8) as r:
            ws_url = json.loads(r.read().decode("utf-8", "replace"))["webSocketDebuggerUrl"]
    except Exception as e:
        return [], f"version fetch: {type(e).__name__}: {str(e)[:80]}"

    ws = None
    try:
        ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True,
                                         max_size=64 * 1024 * 1024)
        ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            msg = json.loads(ws.recv())
            if msg.get("id") != 1:
                continue                                      # an unrelated event, keep reading
            if "error" in msg:
                return [], f"cdp error: {str(msg['error'])[:100]}"
            out: list[tuple[str, str, int]] = []
            for c in (msg.get("result") or {}).get("cookies") or []:
                try:
                    exp = int(float(c.get("expires", -1)))
                except (TypeError, ValueError):
                    exp = -1
                out.append((str(c.get("domain") or ""), str(c.get("name") or ""), max(exp, 0)))
            return out, None
        return [], "no reply to Storage.getCookies within 30s"
    except Exception as e:
        return [], f"{type(e).__name__}: {str(e)[:100]}"
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def read_jar_cdp(port: int) -> tuple[list[tuple[str, str, int]], str | None]:
    """(domain, name, expires_unix) from the LIVE browser over CDP. 0 == session cookie.

    This is the primary reader and the better one regardless of locking: it returns the jar Chrome
    is actually using, including cookies set this session that have not been flushed to SQLite yet.

    Cookie values are handled inside this function and discarded here -- only the domain, the name
    and the expiry integer are returned, so no bearer token can reach a log, a report or stdout.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], "playwright not installed"
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}",
                                                  timeout=CDP_TIMEOUT_MS)
            try:
                out: list[tuple[str, str, int]] = []
                for ctx in browser.contexts:
                    for c in ctx.cookies():
                        exp = c.get("expires", -1)
                        try:
                            exp = int(float(exp))
                        except (TypeError, ValueError):
                            exp = -1
                        out.append((str(c.get("domain") or ""), str(c.get("name") or ""),
                                    max(exp, 0)))
                return out, None
            finally:
                browser.close()                              # detaches only; never closes Chrome
    except Exception as e:
        return [], f"{type(e).__name__}: {str(e)[:120]}"


def emails(subprofile: pathlib.Path) -> list[str]:
    """Account labels only. `account_info` is a display field -- see chrome_auth_audit.py -- so it
    is reported as a label and never as proof of an authenticated session."""
    pref = subprofile / "Preferences"
    if not pref.exists():
        return []
    try:
        d = json.loads(pref.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        return []
    return [a["email"] for a in (d.get("account_info") or []) if isinstance(a, dict) and a.get("email")]


def targets() -> list[dict]:
    out = list(VIDEO_TARGETS)
    if SITES.exists():
        try:
            groups = json.loads(SITES.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            groups = []
        for g in groups if isinstance(groups, list) else []:
            cat = str(g.get("category") or "chat")
            for s in g.get("sites") or []:
                if s.get("url"):
                    out.append({"name": s.get("name") or host_of(s["url"]),
                                "url": s["url"], "category": cat})
    return out


def seats() -> list[dict]:
    """One entry per (profile, chrome_profile). The registry is keyed by provider, so `providers`
    appears twice (flow + rtst share one Chrome); a jar is per-profile, so those collapse."""
    d = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    seen: dict[tuple[str, str], dict] = {}
    for a in d.get("accounts", []):
        prof = a.get("profile")
        if not prof:                                         # digen-01 has port 0 / no profile
            continue
        key = (prof, a.get("chrome_profile") or "Default")
        ent = seen.setdefault(key, {"profile": prof, "chrome_profile": key[1],
                                    "ports": [], "labels": [], "providers": []})
        if a.get("port"):
            ent["ports"].append(a["port"])
        ent["labels"].append(a.get("label"))
        ent["providers"].append(a.get("provider"))
    return list(seen.values())


def audit_seat(seat: dict, tgts: list[dict], now: dt.datetime) -> dict[str, Any]:
    root = PROFILES / seat["profile"]
    sub = root / seat["chrome_profile"]
    row: dict[str, Any] = dict(seat)
    row["profileDir"] = str(root)
    row["subprofileExists"] = sub.exists()
    if not sub.exists():
        row.update(status="NO_PROFILE", cookieTotal=0, sites={})
        return row

    row["accountLabels"] = emails(sub)

    # Raw CDP first (one round trip, touches no tab), then playwright, then the on-disk jar. The
    # disk read only succeeds when the seat's Chrome is closed, so it is genuinely last.
    rows: list[tuple[str, str, int]] = []
    errs: list[str] = []
    for port in sorted(set(seat.get("ports") or [])):
        rows, err = read_jar_cdp_raw(int(port))
        if rows:
            row["readMethod"] = f"cdp-raw:{port}"
            break
        errs.append(f"cdp-raw:{port} {err}")
        rows, err = read_jar_cdp(int(port))
        if rows:
            row["readMethod"] = f"playwright:{port}"
            break
        errs.append(f"playwright:{port} {err}")
    if not rows:
        ck = sub / "Network" / "Cookies"
        if not ck.exists():
            row.update(status="NO_JAR", cookieTotal=0, sites={},
                       note="no cookie file on disk and CDP returned nothing")
            return row
        rows, sql_err = read_jar_sqlite(ck)
        row["readMethod"] = "sqlite"
        if sql_err:
            row.update(status="JAR_UNREADABLE", cookieTotal=0, sites={},
                       error=" | ".join(errs + [f"sqlite: {sql_err}"]),
                       note="a locked jar means Chrome is RUNNING -- it does NOT mean the session "
                            "is gone; fix the reader, do not re-sign-in")
            return row

    now_unix = int(now.timestamp())
    jar: dict[str, dict[str, int]] = {}
    for host, name, exp in rows:
        jar.setdefault(registrable(host), {})[name] = exp
    row["cookieTotal"] = len(rows)
    row["distinctDomains"] = len(jar)

    sites: dict[str, dict] = {}
    for t in tgts:
        dom = registrable(host_of(t["url"]))
        names = jar.get(dom)
        if not names:
            continue                                          # never visited: omit, not "false"
        auth = {n: e for n, e in names.items()
                if any(h in n.lower() for h in AUTH_NAME_HINTS)}
        live = {n: e for n, e in auth.items() if e == 0 or e > now_unix}
        persistent = [n for n, e in live.items() if e]
        if not auth:
            verdict = "visited"
        elif not live:
            verdict = "expired"
        elif not persistent:
            verdict = "session_only"                          # dies with the window
        else:
            verdict = "signed_in_probable"
        sites[t["name"]] = {
            "domain": dom, "category": t["category"], "verdict": verdict,
            "cookiesOnDomain": len(names),
            "authCookieNames": sorted(auth)[:8],              # NAMES only, never values
            "persistentAuthCookies": len(persistent),
        }
    row["sites"] = sites
    ready = [n for n, s in sites.items() if s["verdict"] == "signed_in_probable"]
    row["readySites"] = sorted(ready)
    row["status"] = "READY" if ready else ("VISITED_ONLY" if sites else "EMPTY")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seat", default="", help="only this profile name")
    ap.add_argument("--all-hosts", action="store_true", help="also list every domain in each jar")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    tgts = targets()
    sl = seats()
    if a.seat:
        sl = [s for s in sl if s["profile"] == a.seat]
    print(f"targets: {len(tgts)} sites ({len(VIDEO_TARGETS)} video + "
          f"{len(tgts) - len(VIDEO_TARGETS)} chat)   seats: {len(sl)}")
    print("read-only: cookie NAMES and expiry only, never a value\n")

    report: dict[str, Any] = {
        "generatedAt": now.isoformat(),
        "readOnly": True,
        "verdictMeaning": {
            "signed_in_probable": "auth-named cookie present and unexpired, with a persistent one",
            "session_only": "auth cookie present but dies with the browser window",
            "expired": "auth cookies present but all past expiry -- re-sign-in needed",
            "visited": "cookies on the domain but none auth-shaped -- not signed in",
        },
        "seats": [],
    }

    for seat in sl:
        row = audit_seat(seat, tgts, now)
        if a.all_hosts:
            for port in sorted(set(seat.get("ports") or [])):
                rows, e = read_jar_cdp(int(port))
                if rows:
                    row["allDomains"] = sorted({registrable(h) for h, _, _ in rows})
                    break
        report["seats"].append(row)

        who = f"{row['profile']}/{row['chrome_profile']}"
        ports = ",".join(str(p) for p in sorted(set(row.get("ports") or []))) or "-"
        print(f"=== {who:26s} port {ports:6s} {row['status']}")
        if row.get("accountLabels"):
            print(f"      account label(s): {', '.join(row['accountLabels'])}")
        print(f"      jar: {row.get('cookieTotal', 0)} cookies over "
              f"{row.get('distinctDomains', 0)} domains")
        if row.get("error"):
            print(f"      ERROR {row['error']}")
        for name, s in sorted(row.get("sites", {}).items(),
                              key=lambda kv: (kv[1]["verdict"] != "signed_in_probable", kv[0])):
            mark = {"signed_in_probable": "OK ", "session_only": "~  ",
                    "expired": "EXP", "visited": "   "}[s["verdict"]]
            print(f"      {mark} {name:34s} {s['verdict']:20s} "
                  f"{s['cookiesOnDomain']:3d} ck  auth={','.join(s['authCookieNames'][:3]) or '-'}")
        print()

    ready_any = sorted({n for s in report["seats"] for n in s.get("readySites", [])})
    report["summary"] = {
        "seatsReady": [f"{s['profile']}/{s['chrome_profile']}" for s in report["seats"]
                       if s["status"] == "READY"],
        "seatsNotReady": [f"{s['profile']}/{s['chrome_profile']}" for s in report["seats"]
                          if s["status"] != "READY"],
        "sitesSweepableSomewhere": ready_any,
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"seats READY      : {', '.join(report['summary']['seatsReady']) or 'none'}")
    print(f"seats NOT ready  : {', '.join(report['summary']['seatsNotReady']) or 'none'}")
    print(f"sweepable sites  : {', '.join(ready_any) or 'none'}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
