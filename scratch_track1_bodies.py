import json, sys, urllib.parse, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SECRETS = pathlib.Path(r"d:\omniroute-monetizer\state\secrets")

for name in ["session_meta_ai_web.json", "session_veoaifree_chat_web.json", "session_veoaifree.json"]:
    p = SECRETS / name
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    rx = d.get("recorded_exchange") or {}
    print(f"\n===== {name} =====")
    print("  url:", rx.get("url", "")[:110])
    print("  method:", rx.get("method"))
    body = rx.get("request_body", "")
    print("  body len:", len(body))
    print("  sentinel field:", repr(d.get("sentinel")))
    # show body head
    print("  body head:", body[:400].replace("\n", " "))
    # does body contain the seat's own sentinel?
    sent = d.get("sentinel", "")
    print("  body contains sentinel?", (sent in body) if sent else "n/a")
    print("  body contains 'Omni'?", "Omni" in body)
