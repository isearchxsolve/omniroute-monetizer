import json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
d = json.loads((SEATDIR / "session_cerebras_inference_chat.json").read_text(encoding="utf-8-sig"))
body = d["recorded_exchange"].get("request_body", "")
print("CEREBRAS body len:", len(body))
try:
    obj = json.loads(body)
    print("top-level keys:", list(obj.keys()))
    for k, v in obj.items():
        if k == "messages":
            print(f"  messages: {len(v)} msgs, roles={[m.get('role') for m in v]}")
            for m in v:
                print(f"    [{m.get('role')}] len={len(str(m.get('content','')))}")
        else:
            print(f"  {k}: {str(v)[:120]}")
except Exception as e:
    print("not JSON:", e)
    print(body[:400])
    print("...")
    print(body[-400:])
