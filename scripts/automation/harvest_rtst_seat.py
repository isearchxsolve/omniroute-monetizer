"""harvest_rtst_seat.py -- turn an ALREADY-SIGNED-IN Chrome profile into an rtst.ai pool seat.

Why this exists. state/seat_readiness.json records FOUR automation profiles, each a DIFFERENT Google
account, and rtst.ai reads `signed_in_probable` on every one of them. Only the first was ever
harvested. rtst grants 30 free credits per account (measured: the first spend moved 30 -> 24), so
three unharvested accounts are ~90 credits ~= 15 clips -- and the rtst ADAPTER IS ALREADY BUILT AND
PROVEN (rtst_api_client.py, one clip rendered end-to-end through :8189). So each remaining account is
a token READ, not an adapter build. That is the whole point: breadth on a provider already wired
costs minutes, breadth on 50 unwired providers costs 50 adapters.

What it does NOT do, deliberately:
  * no signup, no login, no password typed or recorded -- the profile is ALREADY signed in
  * no captcha, no card, no plan upgrade. If rtst answers with a wall we stop and say so.
  * never touches the operator's live Chrome. Only state/automation_profiles/<profile>, which is an
    automation profile. Driving the operator's real profile permanently revoked their Google session
    once (2026-08-22, DBSC); that mistake is not repeatable from here because the path is pinned.
  * never prints the token. Length only. The seat file lands in state/secrets/ which is gitignored.

    python harvest_rtst_seat.py --profile seat2                 # launch, read, write, verify
    python harvest_rtst_seat.py --profile seat2 --no-launch     # a Chrome is already on that port
    python harvest_rtst_seat.py --all                           # every unharvested profile in turn
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_no_discard import NO_DISCARD_FLAGS  # noqa: E402  -- stop Chrome discarding idle tabs

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
SECRETS = ROOT / "state" / "secrets"
READINESS = ROOT / "state" / "seat_readiness.json"
AUTOMATION = ROOT / "state" / "automation_profiles"

# Chrome must be launched in a NEW PROCESS GROUP as well as detached: DETACHED_PROCESS alone still
# dies with the parent shell, which is how earlier launches "silently failed" (measured).
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# rtst's SPA keeps its bearer in localStorage. Try the proven key first, then plausible siblings --
# an app rename must not look like "not signed in".
TOKEN_KEYS = ["auth_token", "token", "access_token", "authToken", "jwt"]


def _chrome() -> str:
    for c in CHROME_CANDIDATES:
        if pathlib.Path(c).exists():
            return c
    raise SystemExit("chrome.exe not found in the standard locations")


def _seats() -> list:
    d = json.loads(READINESS.read_text(encoding="utf-8"))
    out = []
    for s in d.get("seats", []):
        ports = s.get("ports") or []
        out.append({
            "profile": s.get("profile"),
            "chrome_profile": s.get("chrome_profile") or "Default",
            "port": int(ports[0]) if ports else None,
            "accounts": s.get("accountLabels") or [],
            "dir": s.get("profileDir") or str(AUTOMATION / str(s.get("profile"))),
        })
    return out


def _cdp_up(port: int, timeout: float = 40.0) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=3) as r:
                return json.loads(r.read().decode("utf-8", "replace")).get("Browser")
        except Exception:
            time.sleep(1.0)
    return None


def launch(seat: dict, url: str = "https://rtst.ai") -> str | None:
    port = seat["port"]
    already = _cdp_up(port, timeout=2.0)
    if already:
        print(f"[=] CDP already listening on {port}: {already}")
        return already
    args = [
        _chrome(),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={seat['dir']}",
        # ALWAYS pin the sub-profile. An unpinned launch opens whichever profile Chrome last used,
        # which is how a harvest silently reads the wrong account's storage.
        f"--profile-directory={seat['chrome_profile']}",
        # Chrome 111+ rejects the DevTools WebSocket with 'Handshake status 403 Forbidden' unless the
        # origin is allowed. Omitting this cost a harvest that then MIS-REPORTED itself as "profile
        # not signed in to rtst" -- a transport failure wearing an auth failure's clothes. The one
        # Chrome that worked (port 9222) had this flag; that is the whole difference.
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--restore-last-session=false",
        *NO_DISCARD_FLAGS,
        url,
    ]
    print(f"[*] launching chrome  profile={seat['profile']}  sub={seat['chrome_profile']}  port={port}")
    subprocess.Popen(args, creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    ver = _cdp_up(port)
    print(f"[{'+' if ver else '!'}] CDP on {port}: {ver or 'DID NOT COME UP'}")
    return ver


def _scan_ls(page) -> tuple[str | None, str | None, list, int]:
    """Try every candidate key. Returns (token, key, tried_labels, unreadable_count).

    unreadable_count is the point of this function. An UNREADABLE key (SecurityError from an opaque
    origin, or a Runtime.evaluate that never answers because the tab is frozen) is categorically
    different from a key that is cleanly ABSENT. Only 'absent' licenses an auth verdict. The first
    version counted only SecurityError, so a 45s evaluate timeout still printed "not signed in" --
    the same defect one layer over.
    """
    tried, blocked = [], 0
    for key in TOKEN_KEYS:
        try:
            v = page.evaluate(f"localStorage.getItem({key!r})", timeout=20)
        except Exception as e:
            msg = str(e)
            blocked += 1
            if "SecurityError" in msg:
                tried.append(f"{key}:UNREADABLE(opaque_origin)")
            elif "did not answer" in msg or isinstance(e, TimeoutError):
                tried.append(f"{key}:UNREADABLE(tab_frozen)")
            else:
                tried.append(f"{key}:UNREADABLE({msg[:44]})")
            continue
        if isinstance(v, str) and len(v) > 40:
            return v, key, tried, blocked
        tried.append(f"{key}:{'short' if isinstance(v, str) else 'absent'}")
    return None, None, tried, blocked


def _fresh_tab(port: int, host: str) -> str | None:
    """Open a BRAND-NEW tab on that Chrome and return a unique match string for it.

    A new tab cannot be discarded or frozen, and it shares the profile's storage, so it is the
    definitive reader when the existing tab is wedged. Marker makes cdp.Page pick this tab and not one
    of the two identical https://rtst.ai/ tabs already open.
    """
    marker = f"omniharvest={port}"
    url = f"https://{host}/?{marker}"
    for method in ("PUT", "GET"):                  # newer Chrome requires PUT on /json/new
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{url}", method=method)
            with urllib.request.urlopen(req, timeout=10) as r:
                json.loads(r.read().decode("utf-8", "replace"))
                return marker
        except Exception:
            continue
    return None


def read_token(port: int, match: str = "rtst.ai") -> tuple[str | None, str | None, str | None]:
    """Return (token, which_key, failure_reason).

    The outcomes are kept DISTINCT on purpose. Earlier versions collapsed them twice: first a CDP
    handshake rejection, then a discarded tab, were BOTH reported as "this profile is not signed in to
    rtst" -- transport and wrong-origin failures wearing an auth failure's clothes, the same error as
    scoring a route dead because its HTML login wall returned 200. A reader must never infer meaning
    from the wrong layer. Only 'localStorage was readable and the key was not in it' is an auth verdict.
    """
    sys.path.insert(0, str(ROOT / "scripts" / "automation"))
    import cdp                                        # the repo's proven raw-CDP helper

    page, last = None, ""
    for attempt in range(4):
        try:
            page = cdp.Page(match=match, port=port)
            break
        except Exception as e:
            last = str(e)[:200]
            if attempt < 3:
                time.sleep(4.0)                        # the SPA may still be loading
    if page is None:
        if "403" in last or "Handshake" in last or "WebSocket" in last:
            return None, None, (f"cdp_handshake_rejected -- Chrome refused the DevTools WebSocket. "
                                f"This says NOTHING about being signed in. Detail: {last[:120]}")
        return None, None, f"no_tab_matching_{match} -- {last[:120]}"

    token, key, tried, blocked = _scan_ls(page)
    if token:
        return token, key, None

    if blocked:
        # Chrome DISCARDS/freezes background tabs. A frozen tab keeps its title and URL in /json, so it
        # looks perfectly alive from outside, but localStorage either throws SecurityError (opaque
        # origin) or Runtime.evaluate never answers. Measured on 9223 and 9225, both listing two live
        # https://rtst.ai/ tabs. Escalate: navigate the tab, then open a brand-new one. Never call any
        # of this "not signed in".
        print(f"[~] {blocked}/{len(TOKEN_KEYS)} reads UNREADABLE -- tab is frozen/opaque, not signed "
              f"out. Waking it, then falling back to a fresh tab")
        try:
            page.send("Page.navigate", {"url": f"https://{match}/"}, timeout=20)
            time.sleep(6.0)
            token, key, tried, blocked = _scan_ls(page)
            if token:
                return token, key, None
        except Exception as e:
            print(f"[~] navigate failed ({str(e)[:70]}) -- going straight to a fresh tab")
            blocked = blocked or 1

        if blocked:
            marker = _fresh_tab(port, match)
            if not marker:
                return None, None, ("could_not_open_fresh_tab -- transport, NOT an auth verdict. "
                                    f"Last read: {', '.join(tried)}")
            time.sleep(8.0)                       # let the SPA boot in the new tab
            try:
                page2 = cdp.Page(match=marker, port=port)
            except Exception as e:
                return None, None, (f"fresh_tab_unattachable -- transport, NOT an auth verdict: "
                                    f"{str(e)[:110]}")
            for _ in range(4):
                token, key, tried, blocked = _scan_ls(page2)
                if token:
                    return token, key, None
                if not blocked:
                    break                          # clean read on a brand-new tab: this IS the truth
                time.sleep(5.0)
            if blocked:
                return None, None, ("unreadable_even_in_a_fresh_tab -- still NOT an auth verdict; the "
                                    f"browser would not answer. Last: {', '.join(tried)}")

    return None, None, ("no_bearer_in_localStorage -- every key read CLEANLY and none held a bearer, so "
                        f"this IS an auth verdict: not signed in to rtst here. Keys: {', '.join(tried)}")


def write_seat(profile: str, token: str, key: str, port: int, account: str) -> pathlib.Path:
    """Write the seat file. Shape is byte-identical to the PROVEN session_rtst_ai.json so that
    session_pool._client_for dispatches on api.kind and needs no new entry for a second account."""
    path = SECRETS / f"session_rtst_ai_{profile}.json"
    payload = {
        "host": "rtst.ai",
        "modality": "video",
        "source": f"cdp:localStorage.{key} ({profile} profile, port {port})",
        "api": {"kind": "rtst", "base": "https://api.rtst.ai", "token": token},
        "context": {"loggedIn": True, "profile": profile, "account": account},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def verify(path: pathlib.Path) -> dict | None:
    """Free reads only -- balance and the cheapest model. Spends nothing."""
    sys.path.insert(0, str(ROOT / "scripts" / "automation"))
    try:
        from rtst_api_client import RtstApiClient
        return RtstApiClient(secret=path).capacity()
    except Exception as e:
        print(f"[!] verify failed: {type(e).__name__}: {str(e)[:160]}")
        return None


def harvest(seat: dict, do_launch: bool = True) -> dict:
    profile, port = seat["profile"], seat["port"]
    account = (seat["accounts"] or ["?"])[0]
    print(f"\n=== {profile}  ({account})  port {port} ===")
    out = {"profile": profile, "account": account, "port": port, "ok": False}
    if port is None:
        out["error"] = "no cdp port recorded for this profile"
        print("[!] " + out["error"])
        return out
    if do_launch and not launch(seat):
        out["error"] = "cdp did not come up"
        return out

    token, key, why = read_token(port)
    if not token:
        out["error"] = why or "unknown read failure"
        print("[!] " + out["error"])
        return out
    print(f"[+] token found in localStorage.{key}  len={len(token)}  (value withheld)")

    path = write_seat(profile, token, key, port, account)
    print(f"[+] wrote {path.name} (gitignored)")
    cap = verify(path)
    if cap:
        out.update(ok=True, credits=cap.get("creditsRemaining"), clips=cap.get("clipsRemaining"))
        print(f"[+] VERIFIED LIVE: {cap.get('creditsRemaining')} credits = "
              f"{cap.get('clipsRemaining')} clip(s) at {(cap.get('cheapest') or {}).get('model')}")
    else:
        out["error"] = "token read but the API refused it -- seat left on disk for inspection"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--profile", help="one profile name from seat_readiness.json")
    ap.add_argument("--all", action="store_true", help="every profile that has no seat file yet")
    ap.add_argument("--no-launch", action="store_true", help="a Chrome is already on that port")
    a = ap.parse_args()

    seats = _seats()
    if a.profile:
        chosen = [s for s in seats if s["profile"] == a.profile]
        if not chosen:
            print(f"no such profile. known: {[s['profile'] for s in seats]}")
            return 2
    elif a.all:
        chosen = [s for s in seats
                  if not (SECRETS / f"session_rtst_ai_{s['profile']}.json").exists()
                  and s["profile"] != "providers"]      # providers is already harvested
    else:
        for s in seats:
            done = (SECRETS / f"session_rtst_ai_{s['profile']}.json").exists()
            print(f"  {s['profile']:12s} port={s['port']}  sub={s['chrome_profile']:12s} "
                  f"acct={(s['accounts'] or ['?'])[0]:28s} seat_file={'yes' if done else 'NO'}")
        return 0

    results = [harvest(s, do_launch=not a.no_launch) for s in chosen]
    live = [r for r in results if r["ok"]]
    print(f"\n{len(live)}/{len(results)} profile(s) became live rtst seats")
    if live:
        tc = sum(int(r.get("clips") or 0) for r in live)
        tk = sum(float(r.get("credits") or 0) for r in live)
        print(f"added: {tk:.0f} credits = {tc} clip(s)")
    for r in results:
        if not r["ok"]:
            print(f"  [OUT] {r['profile']}: {r.get('error')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
