# -*- coding: utf-8 -*-
"""Debug felo body encoding: print raw repr of recorded body and what we send."""
import json

sess = json.load(open(r"d:\omniroute-monetizer\state\secrets\session_felo_ai_web.json", encoding="utf-8"))
rx = sess["recorded_exchange"]
body = rx.get("request_body") or ""
print("type:", type(body))
print("repr first 120:", repr(body[:120]))
print()
# is it valid JSON?
try:
    parsed = json.loads(body)
    print("json.loads OK, type:", type(parsed))
    if isinstance(parsed, dict):
        print("keys:", list(parsed.keys()))
    elif isinstance(parsed, str):
        print("!! parsed to a STRING (double-encoded). inner first 80:", repr(parsed[:80]))
except Exception as e:
    print("json.loads FAILED:", e)
