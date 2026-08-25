#!/usr/bin/env python3
"""Add one more signed-in browser seat to the video fleet, by hand, on purpose.

A "seat" is one Google account == one Chrome profile dir == one --remote-debugging-port == one or
more rows in state/video_accounts.json. Breadth is the whole monetisation strategy (many accounts
across many providers, never one account hammered), so adding a seat needs to be a two-command
routine rather than an afternoon of PowerShell.

Why two commands and not one:

  * Google REFUSES an interactive sign-in in a Chrome started with --remote-debugging-port.
    MEASURED 2026-08-25: the flow lands on accounts.google.com/v3/signin/rejected and then
    /v3/signin/speedbump/changepassword and writes no session cookies at all. So `prepare` starts
    Chrome with NO debug port and ON-SCREEN, the human signs in, and `finish` restarts the same
    profile WITH the port. The session survives because it lives in the profile's cookie jar, not
    in the browser instance.

  * The registry rows are written by `finish`, not `prepare`. If an unsigned seat were registered
    up front, the serve loop's self-heal would see a dead port on the next keepalive tick (every 5
    minutes) and relaunch that profile WITH a debug port -- straight into the sign-in the human is
    still doing, taking the profile lock with it.

Two rules this tool does not bend:

  * PASSWORDS ARE NEVER RECORDED AND NEVER TYPED. `prepare` opens the sign-in page and stops.
  * A CAPTCHA, a card wall, a phone-code wall or a "change your password" speedbump is a STOP,
    reported as-is. Nothing here retries or works around one.

Usage:
    python video_seat.py prepare --tag seat2 --port 9224
    ... sign in by hand in the window that opens, then ...
    python video_seat.py finish  --tag seat2 --port 9224
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import video_provider as vp                       # noqa: E402  (guard + Account live here)
from video_router import ACCOUNTS_FILE, REGISTRY_NOTE, _entry, find_chrome  # noqa: E402

ROOT = HERE.parents[1]
PROFILES = ROOT / "state" / "automation_profiles"

# Chrome's own name for the one sub-profile a freshly created user-data-dir contains. Every seat this
# tool makes is single-profile on purpose: the `niloy` seat was mirrored from a multi-profile Chrome
# and its Local State `last_used` silently pointed at a different sub-profile than the one being
# inspected, which cost most of 2026-08-25 to work out.
SUBPROFILE = "Default"

# The cookies Google only mints for a browser it has actually just signed in. A copied or mirrored
# jar carries SID/SSID/HSID and friends but never these three, so they are the honest test for
# "is this seat signed in" as opposed to "does this seat have Google cookies in it".
FRESH_SESSION_MARKERS = ("LSID", "__Secure-1PSIDTS", "__Secure-3PSIDTS")
SESSION_NAMES = ("SID", "SSID", "HSID", "APISID", "SAPISID", "LSID",
                 "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PSIDTS", "__Secure-3PSIDTS")

WM_CLOSE = 0x0010
DETACHED = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _ps(script: str, timeout: int = 120) -> str:
    """One PowerShell call. Used only for Win32 window handling and process lookup, both of which
    have no usable pure-Python equivalent on Windows."""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                       capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "").strip()


def _browsers_on(udd: pathlib.Path) -> list[int]:
    """Browser (not renderer) pids whose command line names this user-data-dir."""
    out = _ps(f"""
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object {{ $_.CommandLine -like '*{udd.name}*' -and $_.CommandLine -notlike '*--type=*' }} |
  ForEach-Object {{ $_.ProcessId }}
""")
    return [int(x) for x in out.split() if x.strip().isdigit()]


def _port_answering(port: int) -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        s.close()


def _close_gracefully(udd: pathlib.Path, wait: int = 40) -> str:
    """WM_CLOSE, never Stop-Process -Force: Chrome flushes its cookie jar to disk on a clean exit and
    a fresh sign-in can still be in memory. Killing it is how you lose the sign-in you just did."""
    pids = _browsers_on(udd)
    if not pids:
        return "nothing was running"
    _ps("""
Add-Type @"
using System; using System.Runtime.InteropServices;
public class SeatWin { [DllImport("user32.dll")] public static extern IntPtr PostMessage(IntPtr h,uint m,IntPtr w,IntPtr l); }
"@
""" + f"""
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object {{ $_.CommandLine -like '*{udd.name}*' -and $_.CommandLine -notlike '*--type=*' }} |
  ForEach-Object {{
    $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    if ($p -and $p.MainWindowHandle -ne 0) {{
      [void][SeatWin]::PostMessage($p.MainWindowHandle, {WM_CLOSE}, [IntPtr]::Zero, [IntPtr]::Zero)
    }}
  }}
""")
    for i in range(wait):
        time.sleep(1)
        if not _browsers_on(udd):
            return f"closed cleanly in {i + 1}s (cookie jar flushed)"
    return f"STILL RUNNING after {wait}s -- close the window yourself, do not force-kill it"


def _pull_on_screen(udd: pathlib.Path, at: tuple[int, int] = (60, 40)) -> str:
    """Chrome remembers window placement per profile, so a seat that was last run off-screen (the
    keepalive default) reopens off-screen and ignores --window-position. With no debug port there is
    no Browser.setWindowBounds to reach for, so this is Win32. `at` staggers seats prepared in the
    same sitting -- two windows at identical coordinates is how you sign into the wrong one."""
    x, y = at
    return _ps("""
Add-Type @"
using System; using System.Runtime.InteropServices;
public class SeatShow {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr h,int x,int y,int w,int t,bool r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
}
"@
""" + f"""
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object {{ $_.CommandLine -like '*{udd.name}*' -and $_.CommandLine -notlike '*--type=*' }} |
  ForEach-Object {{
    $p = Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    if ($p -and $p.MainWindowHandle -ne 0) {{
      [void][SeatShow]::ShowWindow($p.MainWindowHandle, 9)
      [void][SeatShow]::MoveWindow($p.MainWindowHandle, {x}, {y}, 1300, 900, $true)
      [void][SeatShow]::SetForegroundWindow($p.MainWindowHandle)
      "pulled pid $($p.Id) to {x},{y} 1300x900"
    }}
  }}
""") or "no window handle yet"


def _marker(tag: str, port: int, note: str) -> pathlib.Path:
    """A landing page whose only job is to be unmistakable. The operator signed into the WRONG
    window twice on 2026-08-25 because an automation profile mirrored from their own Chrome shows the
    same avatar and the same name; the tab TITLE was the only reliable tell, so it says so."""
    p = PROFILES / f"SIGN_IN_{tag}.html"
    p.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>&gt;&gt;&gt; SIGN IN HERE: seat {html.escape(tag)} (port {port}) &lt;&lt;&lt;</title>
<style>
 html,body{{margin:0;height:100%;font-family:"Segoe UI",system-ui,sans-serif}}
 body{{background:#14532d;color:#fff;display:flex;align-items:center;justify-content:center}}
 .c{{max-width:960px;padding:44px 56px}} h1{{font-size:44px;margin:0 0 6px;letter-spacing:-.02em}}
 h2{{font-size:21px;font-weight:500;margin:0 0 26px;color:#a7f3d0}}
 p{{font-size:19px;line-height:1.55;margin:0 0 16px;color:#dcfce7}}
 code{{background:rgba(0,0,0,.35);padding:3px 8px;border-radius:5px;font-size:17px}}
 a.b{{display:inline-block;margin-top:12px;background:#fbbf24;color:#14532d;font-size:21px;
     font-weight:700;text-decoration:none;padding:15px 30px;border-radius:10px}}
 .w{{margin-top:30px;padding:15px 20px;border-left:5px solid #fbbf24;background:rgba(0,0,0,.28);
    font-size:17px;color:#fef3c7}}
</style></head><body><div class="c">
<h1>Seat <b>{html.escape(tag)}</b> &mdash; sign in <i>in this window</i>.</h1>
<h2>A brand-new empty profile. Use a Google account you have NOT used for a seat yet.</h2>
<p>Profile dir <code>state\\automation_profiles\\{html.escape(tag)}</code>, debug port
   <code>{port}</code> (not attached yet &mdash; that is deliberate: Google rejects sign-in when a
   debug port is open).</p>
<p>{html.escape(note)}</p>
<a class="b" href="https://accounts.google.com/">Sign in to Google &rarr;</a>
<div class="w">If you hit a CAPTCHA, a phone code, a card/payment wall or "change your password":
   <b>stop and say so.</b> None of those are ever touched by automation.</div>
</div></body></html>
""", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- cookie-jar inspection


def _jar(udd: pathlib.Path) -> dict:
    """What the seat's cookie jar proves. NAMES and COUNTS only -- a cookie value is a bearer token
    and never leaves this function."""
    ck = udd / SUBPROFILE / "Network" / "Cookies"
    out = {"exists": ck.exists(), "google": 0, "session": [], "fresh": [], "rtst": [], "total": 0}
    if not ck.exists():
        return out
    tmp = pathlib.Path(tempfile.mkdtemp()) / "jar.sqlite"
    try:
        shutil.copy2(ck, tmp)                      # Chrome may hold the original open
        con = sqlite3.connect(str(tmp))
        rows = con.execute("SELECT host_key, name FROM cookies").fetchall()
        con.close()
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
        return out
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    out["total"] = len(rows)
    goog = {n for h, n in rows if "google" in h}
    out["google"] = sum(1 for h, _ in rows if "google" in h)
    out["session"] = sorted(goog & set(SESSION_NAMES))
    out["fresh"] = sorted(goog & set(FRESH_SESSION_MARKERS))
    out["rtst"] = sorted({n for h, n in rows if "rtst" in h} & {"token", "idt", "permanent"})
    return out


def _emails(udd: pathlib.Path) -> list[str]:
    pref = udd / SUBPROFILE / "Preferences"
    if not pref.exists():
        return []
    try:
        d = json.loads(pref.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return []
    return [a.get("email") for a in (d.get("account_info") or []) if a.get("email")]


# --------------------------------------------------------------------------- commands


def cmd_prepare(a) -> int:
    udd = vp.safe_profile_dir(a.tag)               # creates it, and asserts it is not the live tree
    vp.assert_safe(udd, who="video_seat prepare")
    if int(a.port) in vp.live_devtools_ports():
        print(f"port {a.port} is advertised by a LIVE Chrome right now -- pick another")
        return 1
    if _port_answering(a.port):
        print(f"port {a.port} is already answering -- pick a free port")
        return 1
    running = _browsers_on(udd)
    if running:
        print(f"a Chrome is already open on this seat (pid {running}) -- sign in there, or run "
              f"`finish` first")
        return 1

    try:
        at = tuple(int(v) for v in a.at.split(",", 1))
    except ValueError:
        print(f"--at wants x,y (got {a.at!r})")
        return 1

    mine = _marker(a.tag, a.port, a.note or
                   "Sign in to Google, and while you are here sign in to any generator you want "
                   "this seat to carry (rtst.ai, digen.ai, ...).")
    chrome = find_chrome()
    fresh = not (udd / SUBPROFILE).exists()
    subprocess.Popen(
        [str(chrome),
         f"--user-data-dir={udd}",
         f"--profile-directory={SUBPROFILE}",      # pinned: never inherit Local State `last_used`
         "--no-first-run", "--no-default-browser-check", "--disable-sync",
         "--window-size=1300,900", f"--window-position={at[0]},{at[1]}",
         mine.as_uri(), "https://accounts.google.com/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        creationflags=DETACHED, close_fds=True)

    for _ in range(20):                            # never report a launch from Popen alone
        time.sleep(1)
        if _browsers_on(udd):
            break
    else:
        print("Chrome did not stay up -- nothing is open")
        return 1
    time.sleep(2)
    log(_pull_on_screen(udd, at))
    log(f"seat {a.tag}: {'new empty' if fresh else 'existing'} profile at {udd}")
    log(f"NO debug port attached (that is what lets Google accept the sign-in)")
    print(f"""
  A green window titled ">>> SIGN IN HERE: seat {a.tag} (port {a.port}) <<<" is now open.
  That title is the only reliable way to tell it from your own Chrome.

  1. Sign in to Google as an account not already used by another seat.
  2. Sign in to any generator you want this seat to carry (rtst.ai, ...).
  3. Then run:  python {pathlib.Path(__file__).name} finish --tag {a.tag} --port {a.port}

  Nothing is typed for you and no password is recorded. A CAPTCHA / phone / card / password-change
  wall means stop -- say so instead of pushing through it.""")
    return 0


def cmd_finish(a) -> int:
    udd = vp.safe_profile_dir(a.tag)
    vp.assert_safe(udd, who="video_seat finish")
    log(f"closing the sign-in window: {_close_gracefully(udd)}")
    if _browsers_on(udd):
        return 1

    jar, mails = _jar(udd), _emails(udd)
    print(f"\n  cookie jar   : {jar['total']} rows, {jar['google']} google-scoped")
    print(f"  session names: {jar['session'] or 'NONE'}")
    print(f"  fresh markers: {jar['fresh'] or 'NONE'}   (need all of {list(FRESH_SESSION_MARKERS)})")
    print(f"  account_info : {mails or 'NONE'}")
    print(f"  rtst auth    : {jar['rtst'] or 'none'}")
    if len(jar["fresh"]) < len(FRESH_SESSION_MARKERS):
        print(f"\n  NOT SIGNED IN. The fresh-session cookies Google mints on a real sign-in are "
              f"missing, so this seat would fail its first probe. Nothing was registered.\n"
              f"  Re-run `prepare --tag {a.tag} --port {a.port}` and complete the sign-in, or say "
              f"what wall you hit.")
        return 1

    # Register only now, and only what the jar can actually back: a row for a provider this seat has
    # no session for is a permanently-DOWN account the self-heal will retry every 5 minutes forever.
    want = [p.strip().lower() for p in a.providers.split(",") if p.strip()]
    if "rtst" in want and not jar["rtst"]:
        print(f"  skipping the rtst row: no rtst.ai auth cookie in this seat")
        want = [p for p in want if p != "rtst"]

    raw = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8")) if ACCOUNTS_FILE.exists() \
        else {"_note": REGISTRY_NOTE, "accounts": []}
    existing = raw.setdefault("accounts", [])
    added = []
    for prov in want:
        adapter = vp.get(prov)
        if adapter is None:
            print(f"  no adapter for provider {prov!r} -- skipped")
            continue
        label = f"{prov}-{a.tag}"
        if any(e.get("label") == label for e in existing):
            print(f"  {label} is already registered -- left as it is")
            continue
        existing.append(_entry({"label": label, "provider": prov, "port": a.port,
                                "profile": a.tag, "chrome_profile": SUBPROFILE,
                                "enabled": True, "url": adapter.default_url}))
        added.append(label)
    raw.setdefault("_note", REGISTRY_NOTE)
    ACCOUNTS_FILE.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    print(f"\n  registered   : {added or 'nothing new'} -> {ACCOUNTS_FILE.name}")
    print(f"\n  next: python video_router.py wake     (relaunches this seat WITH port {a.port}, "
          f"off-screen, and probes it)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prepare", help="open a fresh profile ON-SCREEN with NO debug port, for a "
                                       "hand sign-in")
    p.add_argument("--tag", required=True, help="profile dir name under state/automation_profiles")
    p.add_argument("--port", type=int, required=True, help="the debug port this seat will own once "
                                                           "it is signed in")
    p.add_argument("--note", default="", help="extra line shown on the landing page")
    p.add_argument("--at", default="60,40", metavar="X,Y",
                   help="where to put the window; stagger seats prepared in the same sitting")
    p.set_defaults(fn=cmd_prepare)

    f = sub.add_parser("finish", help="close the window, verify the session, register the rows")
    f.add_argument("--tag", required=True)
    f.add_argument("--port", type=int, required=True)
    f.add_argument("--providers", default="flow,rtst",
                   help="comma-separated providers to register for this seat (default flow,rtst)")
    f.set_defaults(fn=cmd_finish)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
