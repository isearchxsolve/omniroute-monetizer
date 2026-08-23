"""Which local Chrome profile actually holds a LIVE Google session?

WHY THIS IS AN HONEST QUESTION, NOT A BYPASS:
kie.ai's Google chooser listed `isearch.xsolve@gmail.com` as "Signed out", so the robot profile
has the account registered but no working session. The operator asked whether it can be restored.
Restoring means finding a profile that still holds UNEXPIRED Google auth cookies -- not inventing
them. Per the standing rules this script therefore:
  - opens every Cookies database READ-ONLY, on a copy, and never writes to any profile
  - reads only cookie NAME, HOST and EXPIRY -- never a value (values are DPAPI-encrypted anyway)
  - never fabricates, injects or edits a cookie
  - reports "no live session" plainly if that is the answer

The cookies that carry a Google web session are the __Secure-*PSID / SID / HSID / SSID family. If
those are absent or expired everywhere, the honest answer is that only a human sign-in can restore
it, and this script says so.

Chrome stores expiry as microseconds since 1601-01-01 (the Windows FILETIME epoch).
"""
from __future__ import annotations

import datetime as dt
import pathlib
import shutil
import sqlite3
import tempfile

ROOT = pathlib.Path(r"D:\omniroute-monetizer\state")
CANDIDATES = [
    ROOT / "automation_profiles" / "providers",
    ROOT / "automation_profiles" / "harvest_profile",
    ROOT / "automation_profiles" / "x",
    ROOT / "automation_profiles" / "selftest",
    ROOT / "automation_profiles" / "guard_smoketest",
    ROOT / "browser_profile",
    ROOT / "harvest_profile",
]

# The cookies that actually constitute a signed-in Google web session.
SESSION_NAMES = {"SID", "HSID", "SSID", "APISID", "SAPISID", "__Secure-1PSID",
                 "__Secure-3PSID", "__Secure-1PSIDTS", "__Secure-3PSIDTS", "LSID"}
# __Host-GAPS is NOT one of them. MEASURED 2026-08-23: every profile on this machine carries an
# unexpired __Host-GAPS for accounts.google.com while Google's own account chooser reports
# `isearch.xsolve@gmail.com` as "Signed out". GAPS is an anti-abuse / account-chooser cookie; it
# survives sign-out and proves nothing about authentication. Counting it made the first run of this
# script conclude "a restore may be possible" when the truth was the exact opposite. Kept here,
# separately, so the distinction is visible rather than silently dropped.
NON_SESSION_NAMES = {"__Host-GAPS"}
EPOCH = dt.datetime(1601, 1, 1, tzinfo=dt.timezone.utc)


def chrome_time(us: int) -> dt.datetime | None:
    if not us:
        return None
    try:
        return EPOCH + dt.timedelta(microseconds=int(us))
    except Exception:
        return None


def scan(cookie_db: pathlib.Path) -> dict:
    """Copy the db out (Chrome may hold a lock) and read cookie metadata only."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td) / "Cookies"
        try:
            shutil.copy2(cookie_db, tmp)
        except Exception as exc:
            return {"error": f"copy failed: {type(exc).__name__}"}
        for extra in ("-wal", "-shm"):
            src = cookie_db.with_name(cookie_db.name + extra)
            if src.exists():
                try:
                    shutil.copy2(src, tmp.with_name(tmp.name + extra))
                except Exception:
                    pass
        try:
            con = sqlite3.connect(f"file:{tmp.as_posix()}?mode=ro", uri=True, timeout=20)
        except Exception as exc:
            return {"error": f"open failed: {type(exc).__name__}"}
        try:
            rows = con.execute(
                "SELECT host_key, name, expires_utc, is_secure FROM cookies "
                "WHERE host_key LIKE '%google.com'").fetchall()
        except Exception as exc:
            con.close()
            return {"error": f"query failed: {type(exc).__name__}"}
        con.close()

    now = dt.datetime.now(dt.timezone.utc)
    found, live, noise = [], [], []
    for host, name, exp, _sec in rows:
        when = chrome_time(exp)
        alive = when is None or when > now          # expires_utc 0 == session cookie
        if name in NON_SESSION_NAMES:
            if alive:
                noise.append(name)
            continue
        if name not in SESSION_NAMES:
            continue
        found.append(name)
        if alive:
            live.append((name, host, when.date().isoformat() if when else "session"))
    return {"google_cookies_total": len(rows), "session_cookies": sorted(set(found)),
            "live": live, "non_session_present": sorted(set(noise))}


print("Chrome should be CLOSED for a clean read; every open below is read-only on a copy.")
print()
verdict_any = False
for prof in CANDIDATES:
    db = None
    for rel in ("Default/Cookies", "Default/Network/Cookies", "Cookies", "Network/Cookies"):
        p = prof / rel
        if p.exists():
            db = p
            break
    print("=" * 84)
    print(f"{prof}")
    if not prof.exists():
        print("   profile directory does not exist")
        continue
    if db is None:
        print("   no Cookies database found -> this profile has never held a web session")
        continue
    info = scan(db)
    if "error" in info:
        print(f"   {info['error']}")
        continue
    print(f"   cookies db      : {db.relative_to(prof)}")
    print(f"   google cookies  : {info['google_cookies_total']}")
    print(f"   session cookies : {', '.join(info['session_cookies']) or '(none)'}")
    if info.get("non_session_present"):
        print(f"   (ignored        : {', '.join(info['non_session_present'])}"
              f" -- survives sign-out, proves nothing)")
    if info["live"]:
        verdict_any = True
        print(f"   LIVE, UNEXPIRED : {len(info['live'])}")
        for name, host, until in info["live"]:
            print(f"        {name:<20} {host:<24} expires {until}")
    else:
        print("   LIVE, UNEXPIRED : none")

print()
print("=" * 84)
if verdict_any:
    print("  At least one profile still holds unexpired Google session cookies.")
    print("  A restore may be possible by pointing the robot at THAT profile -- no password needed.")
else:
    print("  NO profile holds a live Google session cookie.")
    print("  Honest conclusion: this cannot be restored by me. Only a human sign-in can create a")
    print("  new session, because the only remaining path is entering a password / passing MFA,")
    print("  which I must not do.")
