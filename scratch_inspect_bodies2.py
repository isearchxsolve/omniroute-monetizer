import json, sys, urllib.parse
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

# cerebras full body
d = json.loads((SEATDIR / "session_cerebras_inference_chat.json").read_text(encoding="utf-8-sig"))
body = d["recorded_exchange"].get("request_body", "")
print("CEREBRAS body (full):")
print(body[:1200])
print()

# gemini: check which sentinel forms exist in the body
g = json.loads((SEATDIR / "session_google_gemini_web.json").read_text(encoding="utf-8-sig"))
gb = g["recorded_exchange"].get("request_body", "")
print(f"GEMINI body len={len(gb)}")
ph = "Reply exactly one word: Omni."
print("  literal in body:", ph in gb)
print("  quote_plus in body:", urllib.parse.quote_plus(ph) in gb)
print("  quote in body:", urllib.parse.quote(ph) in gb)
idx = gb.find("Omni")
print("  context around Omni:", repr(gb[max(0,idx-80):idx+40]))
