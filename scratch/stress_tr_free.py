"""Stress-test TokenRouter's free model: is it unlimited or does it throttle?

Fire 12 rapid sequential calls at qwen3.8-max-free and record status + any
rate-limit headers. If all 200 with no 429, the free model is effectively
unlimited for parallel use.
"""
import time

import requests

KEY = "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"  # key2
URL = "https://api.tokenrouter.com/v1/chat/completions"

results = []
for i in range(12):
    t0 = time.time()
    try:
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {KEY}"},
            json={
                "model": "qwen/qwen3.8-max-free",
                "messages": [{"role": "user", "content": f"Reply with the number {i}"}],
                "max_tokens": 16,
                "stream": False,
            },
            timeout=60,
        )
        dt = time.time() - t0
        rl = {k: v for k, v in r.headers.items()
              if any(t in k.lower() for t in ("rate", "limit", "quota", "remaining", "retry"))}
        results.append((r.status_code, round(dt, 1), rl))
        print(f"  call {i+1:2d}: {r.status_code} in {dt:.1f}s {rl if rl else ''}")
    except Exception as e:
        print(f"  call {i+1:2d}: ERR {type(e).__name__}")
        results.append((0, 0, str(e)[:40]))

ok = sum(1 for s, _, _ in results if s == 200)
print(f"\n{ok}/12 returned 200 OK")
if ok == 12:
    print("VERDICT: free model shows NO throttling on rapid sequential use")
else:
    print("VERDICT: throttling/errors present")
