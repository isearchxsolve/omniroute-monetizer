"""Track 2: refresh the 3 AUTH-EXPIRED seats with freshly harvested credentials.

groq    -> patch recorded_exchange.request_headers.authorization = Bearer <fresh stytch JWT>
cerebras-> patch top-level cookie_header (merge harvested authjs.session-token + cf_clearance)
gemini  -> patch top-level cookie_header (re-harvest .google.com SID family)

Then set runtime=replay so the pool dispatches them stateless. Writes seat files
(secrets, gitignored). Prints a diff summary; never prints full secrets.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from cdp import Page, pick_page  # noqa: E402

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
HARVEST = SEATDIR / "expired_seat_reauth_harvest.json"


def parse_cookie_header(ch: str) -> dict:
    out = {}
    for part in ch.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def build_cookie_header(d: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in d.items())


def get_cookies_for(domain_substr: str, port: int = 9222) -> list:
    """Pull ALL browser cookies, filter by domain substring (handles .google.com)."""
    # Use any page target to get browser-level cookies via Network.getAllCookies
    t = pick_page("", port)
    with Page("", port=port) as p:
        r = p.send("Network.getAllCookies")
    cookies = r.get("cookies", [])
    return [c for c in cookies if domain_substr in c.get("domain", "")]


def patch_groq():
    seat = SEATDIR / "session_groq_chat.json"
    d = json.loads(seat.read_text(encoding="utf-8-sig"))
    h = json.loads(HARVEST.read_text(encoding="utf-8"))
    info = h.get("session_groq_free_console.json", {})
    jwt = None
    for c in info.get("cookies", []):
        if c["name"] == "stytch_session_jwt":
            jwt = c["value"]
    if not jwt:
        print("  GROQ: no stytch_session_jwt harvested - ABORT")
        return False
    old = d["recorded_exchange"]["request_headers"].get("authorization", "")
    d["recorded_exchange"]["request_headers"]["authorization"] = f"Bearer {jwt}"
    d["runtime"] = "replay"
    d["updated_at"] = int(time.time())
    d.setdefault("status", {})["alive"] = True
    d["status"]["reauth_at"] = int(time.time())
    seat.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"  GROQ: authorization Bearer refreshed (old len={len(old)}, new len={len(jwt)+7})")
    return True


def patch_cerebras():
    seat = SEATDIR / "session_cerebras_inference_chat.json"
    d = json.loads(seat.read_text(encoding="utf-8-sig"))
    h = json.loads(HARVEST.read_text(encoding="utf-8"))
    info = h.get("session_cerebras_chat.json", {})
    harvested = {c["name"]: c["value"] for c in info.get("cookies", [])}
    if "authjs.session-token" not in harvested:
        print("  CEREBRAS: no authjs.session-token harvested - ABORT")
        return False
    merged = parse_cookie_header(d.get("cookie_header", ""))
    merged.update(harvested)  # fresh values win
    old_len = len(d.get("cookie_header", ""))
    d["cookie_header"] = build_cookie_header(merged)
    d["runtime"] = "replay"
    d["updated_at"] = int(time.time())
    d.setdefault("status", {})["alive"] = True
    d["status"]["reauth_at"] = int(time.time())
    seat.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"  CEREBRAS: cookie_header refreshed (old len={old_len}, new len={len(d['cookie_header'])}, "
          f"authjs.session-token len={len(harvested['authjs.session-token'])})")
    return True


def patch_gemini():
    seat = SEATDIR / "session_google_gemini_web.json"
    d = json.loads(seat.read_text(encoding="utf-8-sig"))
    # Re-harvest with .google.com domain to catch SID family
    cookies = get_cookies_for("google.com")
    harvested = {}
    for c in cookies:
        # keep cookies relevant to gemini/google auth
        harvested[c["name"]] = c["value"]
    sid_names = [n for n in harvested if n in ("SID", "SSID", "HSID", "SAPISID", "APISID",
                                               "SECURE_LOGIN_AT", "COMPASS", "__Secure-1PSID",
                                               "__Secure-3PSID", "__Secure-1PAPISID")]
    if "SID" not in harvested and "__Secure-1PSID" not in harvested:
        print(f"  GEMINI: no SID-family cookie found among {len(harvested)} google.com cookies - ABORT")
        print(f"    names: {sorted(harvested.keys())[:40]}")
        return False
    merged = parse_cookie_header(d.get("cookie_header", ""))
    merged.update(harvested)
    old_len = len(d.get("cookie_header", ""))
    d["cookie_header"] = build_cookie_header(merged)
    d["runtime"] = "replay"
    d["updated_at"] = int(time.time())
    d.setdefault("status", {})["alive"] = True
    d["status"]["reauth_at"] = int(time.time())
    seat.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"  GEMINI: cookie_header refreshed (old len={old_len}, new len={len(d['cookie_header'])}, "
          f"google.com cookies={len(harvested)}, SID-family={sid_names})")
    return True


def main():
    ok = []
    ok.append(("groq", patch_groq()))
    ok.append(("cerebras", patch_cerebras()))
    ok.append(("gemini", patch_gemini()))
    print("\nRESULT:")
    for name, r in ok:
        print(f"  {name}: {'PATCHED' if r else 'FAILED'}")


if __name__ == "__main__":
    main()
