import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
for name in ["session_groq_chat.json", "session_cerebras_inference_chat.json", "session_google_gemini_web.json"]:
    p = SEATDIR / name
    if not p.exists():
        # search
        hits = list(SEATDIR.glob("*groq*")) + list(SEATDIR.glob("*cerebras*")) + list(SEATDIR.glob("*gemini*"))
        print(f"NOT FOUND {name}; candidates: {[h.name for h in hits]}")
        continue
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    print(f"\n=== {name}")
    for k, v in d.items():
        if isinstance(v, str):
            print(f"  {k}: str len={len(v)} = {v[:70]}")
        elif isinstance(v, dict):
            print(f"  {k}: dict keys={list(v.keys())[:12]}")
        elif isinstance(v, list):
            print(f"  {k}: list len={len(v)}")
        else:
            print(f"  {k}: {v!r}")
