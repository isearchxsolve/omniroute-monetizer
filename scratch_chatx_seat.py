import json, sys, urllib.parse
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
# find chatx seat
hits = list(SEATDIR.glob("*chatx*"))
print("chatx seats:", [h.name for h in hits])
for h in hits:
    d = json.loads(h.read_text(encoding="utf-8-sig"))
    print(f"\n=== {h.name}")
    for k, v in d.items():
        if k == "recorded_exchange":
            ex = v
            print(f"  recorded_exchange.url: {ex.get('url')}")
            print(f"  recorded_exchange.method: {ex.get('method')}")
            body = ex.get("request_body", "")
            print(f"  body len={len(body)}")
            fields = dict(urllib.parse.parse_qsl(body))
            print(f"  body fields: {list(fields.keys())}")
            for fk in ["_token", "user_id", "chats_id", "current_model", "prompt", "is_web", "is_youtube"]:
                if fk in fields:
                    print(f"    {fk}: {fields[fk][:60]!r}")
            hdrs = ex.get("request_headers", {})
            print(f"  headers: {[k for k in hdrs if not k.startswith(':')]}")
        elif isinstance(v, str):
            print(f"  {k}: str len={len(v)} = {v[:60]!r}")
        elif isinstance(v, dict):
            print(f"  {k}: dict keys={list(v.keys())[:10]}")
        else:
            print(f"  {k}: {v!r}")
