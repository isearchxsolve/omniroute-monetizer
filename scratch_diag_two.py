import json, sys, urllib.parse
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

# --- gemini injection trace ---
g = UniversalSessionClient(str(SEATDIR / "session_google_gemini_web.json"))
body = g.base_body
ph = "Reply exactly one word: Omni."
print("GEMINI base_body len:", len(body))
print("  literal in body:", ph in body)
print("  quote_plus in body:", urllib.parse.quote_plus(ph) in body)
print("  quote in body:", urllib.parse.quote(ph) in body)
# is_json detection
stripped = body.lstrip()
is_json = stripped[:1] in ("{", "[") or '{"' in body
print("  is_json detected:", is_json)
# try inject
try:
    out = g._inject_prompt("TESTPROMPT123")
    print("  inject result == base:", out == body)
    print("  TESTPROMPT123 in out:", "TESTPROMPT123" in out)
    print("  quote(TESTPROMPT123) in out:", urllib.parse.quote("TESTPROMPT123") in out)
except Exception as e:
    print("  inject raised:", e)

# --- cerebras: fire and capture the real 400 body ---
print("\nCEREBRAS 400 diagnosis:")
c = UniversalSessionClient(str(SEATDIR / "session_cerebras_inference_chat.json"))
import curl_cffi
from curl_cffi.requests import Session as CCSession
s = CCSession(impersonate="chrome")
body_bytes = c.base_body.encode("utf-8")
r = s.request(c.method, c.url, headers=c.headers, data=body_bytes, timeout=60)
print("  status:", r.status_code)
print("  body[:600]:", r.text[:600])
