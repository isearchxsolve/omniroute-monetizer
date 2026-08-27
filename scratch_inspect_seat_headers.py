import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
for name in ["session_groq_chat.json", "session_cerebras_inference_chat.json", "session_google_gemini_web.json"]:
    d = json.loads((SEATDIR / name).read_text(encoding="utf-8-sig"))
    ex = d.get("recorded_exchange", {})
    print(f"\n=== {name}")
    print(f"  url: {ex.get('url')}")
    print(f"  method: {ex.get('method')}")
    hdrs = ex.get("request_headers", {})
    for k, v in hdrs.items():
        if k.startswith(":"):
            continue
        vv = str(v)
        print(f"  HDR {k}: len={len(vv)} = {vv[:80]}")
    print(f"  body[:120]: {str(ex.get('request_body',''))[:120]}")
