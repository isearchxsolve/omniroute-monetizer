#!/usr/bin/env python3
import requests
import time

t0 = time.perf_counter()
r = requests.post(
    "http://127.0.0.1:20128/v1/chat/completions",
    json={"model": "frontier", "messages": [{"role": "user", "content": "hello"}]},
    timeout=15
)
dur = (time.perf_counter() - t0) * 1000
print(f"[+] HTTP {r.status_code} in {dur:.1f}ms -> Text: {r.text[:200]}")
