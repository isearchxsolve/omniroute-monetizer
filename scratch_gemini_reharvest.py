"""Re-harvest gemini cookies correctly: Network.getCookies scoped to the gemini URL.

getAllCookies + domain-substring pulled 42 cookies across ALL signed-in Google
accounts (duplicates, cross-account). Network.getCookies with urls= returns
exactly the cookie set the browser would send for that origin -- no pollution.
Then rebuild the seat cookie_header from ONLY those, dedup by name (last wins).
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
SEAT = SEATDIR / "session_google_gemini_web.json"

with Page("gemini.google.com", port=9222) as p:
    r = p.send("Network.getCookies", {"urls": ["https://gemini.google.com/"]})
cookies = r.get("cookies", [])
print(f"cookies scoped to gemini.google.com: {len(cookies)}")

# Dedup by name, keep the one with the most specific domain (prefer non-.google.com
# when both exist, but for auth the .google.com SID family is what matters).
by_name = {}
for c in cookies:
    n = c["name"]
    if n not in by_name:
        by_name[n] = c
    else:
        # prefer longer/more specific value; keep first otherwise
        pass
names = sorted(by_name.keys())
print("names:", names)
sid_family = [n for n in names if n in ("SID","SSID","HSID","APISID","SAPISID",
              "__Secure-1PSID","__Secure-3PSID","__Secure-1PAPISID","__Secure-3PAPISID")]
print("SID family present:", sid_family)

header = "; ".join(f"{c['name']}={c['value']}" for c in by_name.values())
print("new header len:", len(header))

d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
d["cookie_header"] = header
d["runtime"] = "replay"
d["updated_at"] = int(time.time())
d.setdefault("status", {})["alive"] = True
d["status"]["reauth_at"] = int(time.time())
SEAT.write_text(json.dumps(d, indent=1), encoding="utf-8")
print("PATCHED gemini seat with scoped cookie set")
