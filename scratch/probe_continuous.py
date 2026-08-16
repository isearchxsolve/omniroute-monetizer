"""Continuous 8-minute probe: hit /v1/models every 5s, log any response > 3s.

Purpose: detect residual periodic event-loop stalls after CredentialHealth disable.
"""
import time
import datetime
import requests

BASE = "http://localhost:20128"
DURATION = 480  # 8 minutes
INTERVAL = 5
stalls = []
start = time.time()
n = 0
while time.time() - start < DURATION:
    t0 = time.time()
    try:
        r = requests.get(f"{BASE}/v1/models", timeout=45)
        dt = time.time() - t0
        n += 1
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if dt > 3.0:
            stalls.append((ts, dt, r.status_code))
            print(f"[{ts}] STALL probe {n}: {dt:.2f}s HTTP {r.status_code}", flush=True)
        elif n % 12 == 0:  # heartbeat every ~60s
            print(f"[{ts}] ok probe {n}: {dt:.2f}s", flush=True)
    except Exception as e:
        dt = time.time() - t0
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        stalls.append((ts, dt, str(e)[:60]))
        print(f"[{ts}] ERROR probe {n}: {dt:.2f}s {type(e).__name__}", flush=True)
    # sleep remaining interval
    elapsed = time.time() - t0
    if elapsed < INTERVAL:
        time.sleep(INTERVAL - elapsed)

print(f"\nDONE: {n} probes over {DURATION}s, {len(stalls)} stalls >3s")
for ts, dt, info in stalls:
    print(f"  {ts}: {dt:.2f}s ({info})")
