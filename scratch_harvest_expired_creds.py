"""Harvest fresh credentials for the 3 AUTH-EXPIRED seats from their live tabs.

Seats: groq (Bearer JWT), cerebras (cookie), gemini (cookie).
All three have live signed-in tabs on port 9222 (verified).

Method: attach to the live tab via CDP, pull Network.getAllCookies (includes
HttpOnly) + scan localStorage/sessionStorage for bearer tokens. Write to a
scratch secrets file (never committed), then patch the seat files.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from cdp import Page, pick_page  # noqa: E402

SECRETS = Path(r"d:\omniroute-monetizer\state\secrets")
SECRETS.mkdir(parents=True, exist_ok=True)
OUT = SECRETS / "expired_seat_reauth_harvest.json"

SEATS = [
    # (seat file, tab match, host for cookie filter)
    ("session_groq_free_console.json", "console.groq.com", "groq.com"),
    ("session_cerebras_chat.json", "chat.cerebras.ai", "cerebras.ai"),
    ("session_gemini_google_web.json", "gemini.google.com", "gemini.google.com"),
]

JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


def harvest(match: str, host: str, port: int = 9222) -> dict:
    t = pick_page(match, port)
    print(f"\n=== {match} -> {t.get('url', '')[:80]}")
    out = {"tab_url": t.get("url"), "cookies": [], "cookie_header": "",
           "local_storage": {}, "session_storage": {}, "bearers": []}
    with Page(match, port=port) as p:
        # 1. All cookies for this page context (incl. HttpOnly)
        r = p.send("Network.getAllCookies")
        cookies = r.get("cookies", [])
        mine = [c for c in cookies if host in c.get("domain", "")]
        out["cookies"] = mine
        out["cookie_header"] = "; ".join(f"{c['name']}={c['value']}" for c in mine)
        print(f"  cookies: {len(cookies)} total, {len(mine)} for {host}")
        # 2. localStorage + sessionStorage scan
        try:
            ls = p.evaluate("JSON.stringify(Object.entries(localStorage))")
            out["local_storage"] = dict(json.loads(ls or "[]"))
        except Exception as e:
            print(f"  localStorage: {e}")
        try:
            ss = p.evaluate("JSON.stringify(Object.entries(sessionStorage))")
            out["session_storage"] = dict(json.loads(ss or "[]"))
        except Exception as e:
            print(f"  sessionStorage: {e}")
        # 3. Find JWTs anywhere in storage
        blob = json.dumps(out["local_storage"]) + json.dumps(out["session_storage"])
        out["bearers"] = sorted(set(JWT_RE.findall(blob)))
        for k, v in out["local_storage"].items():
            if isinstance(v, str) and len(v) < 200:
                print(f"    LS[{k}] = {v[:120]}")
        print(f"  bearers found: {len(out['bearers'])}")
        for b in out["bearers"][:3]:
            print(f"    JWT: {b[:60]}...")
    return out


def main():
    results = {}
    for seat, match, host in SEATS:
        try:
            results[seat] = harvest(match, host)
        except SystemExit as e:
            print(f"  SKIP {seat}: {e}")
            results[seat] = {"error": str(e)}
        except Exception as e:
            print(f"  ERROR {seat}: {e}")
            results[seat] = {"error": str(e)}
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nSaved harvest -> {OUT} (SECRETS - never commit)")


if __name__ == "__main__":
    main()
