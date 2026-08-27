import json, sys, urllib.parse
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
g = json.loads((SEATDIR / "session_google_gemini_web.json").read_text(encoding="utf-8-sig"))
gb = g["recorded_exchange"].get("request_body", "")
print("body len:", len(gb))
# parse form fields
fields = urllib.parse.parse_qs(gb, keep_blank_values=True)
print("form field keys:", list(fields.keys()))
for k in fields:
    v = fields[k][0]
    print(f"  {k}: len={len(v)} = {v[:80]!r}")
# is there an at= ?
print("\n'at=' present:", "at=" in gb)
print("'&at=' present:", "&at=" in gb)
