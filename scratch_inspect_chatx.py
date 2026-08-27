# -*- coding: utf-8 -*-
import json
sess = json.load(open(r"d:\omniroute-monetizer\state\secrets\session_chatx.json", encoding="utf-8"))
rx = sess["recorded_exchange"]
print("url:", rx["url"])
print("method:", rx.get("method"))
print("headers:")
for k, v in (rx.get("request_headers") or {}).items():
    if k.lower() in ("authorization", "cookie", "x-csrf-token"):
        print("  %s: %s...(len=%d)" % (k, v[:25], len(v)))
    else:
        print("  %s: %s" % (k, v))
body = rx.get("request_body") or ""
print("body (len=%d):" % len(body))
print(body[:600])
