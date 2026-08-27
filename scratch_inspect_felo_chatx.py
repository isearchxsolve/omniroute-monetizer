# -*- coding: utf-8 -*-
"""Inspect felo + chatx recorded exchanges to understand the 2-step flow shape."""
import glob
import json

for f in glob.glob(r"d:\omniroute-monetizer\state\secrets\session_*.json"):
    if not any(k in f for k in ("felo", "chatx")):
        continue
    print("=" * 70)
    print(f.split("\\")[-1])
    d = json.load(open(f, encoding="utf-8"))
    rx = d.get("recorded_exchange", {})
    print("host:", d.get("host"))
    print("url:", rx.get("url"))
    print("method:", rx.get("method"))
    print("--- request_headers (redacted) ---")
    for k, v in (rx.get("request_headers") or {}).items():
        v = str(v)
        print("  %s: %s" % (k, v[:60] + ("...(len=%d)" % len(v) if len(v) > 60 else "")))
    print("--- request_body (first 800) ---")
    print((rx.get("request_body") or "")[:800])
    print()
