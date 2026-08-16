"""4x latency probe against /v1/models to prove the 37s stall is gone."""
import time
import requests

BASE = "http://localhost:20128"
results = []
for i in range(4):
    t0 = time.time()
    try:
        r = requests.get(f"{BASE}/v1/models", timeout=45)
        dt = time.time() - t0
        n = len(r.json().get("data", [])) if r.status_code == 200 else 0
        results.append(dt)
        print(f"probe {i+1}: {dt:.2f}s  HTTP {r.status_code}  models={n}")
    except Exception as e:
        dt = time.time() - t0
        results.append(dt)
        print(f"probe {i+1}: {dt:.2f}s  ERROR {e}")

worst = max(results)
print(f"\nworst probe: {worst:.2f}s")
print("STALL ELIMINATED" if worst < 10 else "STALL STILL PRESENT")
