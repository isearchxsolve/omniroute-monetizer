"""Post-fix live stall monitor. Probes /v1/models every 2s for DURATION seconds.
Old behavior: 30-38s freezes every ~94-101s (60s TTL + 30s stale window).
Expected after fix: at most ONE residual stall (last entry built under old TTL),
then silence for ~10 min. Any stall is logged with latency.
"""
import time
import datetime
import requests

BASE = "http://localhost:20128"
DURATION = 180
STALL_THRESHOLD = 3.0

start = time.time()
last_probe = 0.0
stalls = []
probes = 0
while time.time() - start < DURATION:
    if time.time() - last_probe >= 2.0:
        last_probe = time.time()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        t0 = time.time()
        try:
            r = requests.get(f"{BASE}/v1/models", timeout=60)
            dt = time.time() - t0
            probes += 1
            if dt > STALL_THRESHOLD:
                stalls.append((ts, dt, r.status_code))
                print(f"[{ts}] STALL {dt:.2f}s status={r.status_code}", flush=True)
            else:
                print(f"[{ts}] ok {dt:.2f}s", flush=True)
        except Exception as e:
            dt = time.time() - t0
            probes += 1
            stalls.append((ts, dt, type(e).__name__))
            print(f"[{ts}] ERR {dt:.2f}s {type(e).__name__}", flush=True)
    time.sleep(0.2)

print(f"\nSUMMARY: {probes} probes over {DURATION}s, {len(stalls)} stalls >{STALL_THRESHOLD}s")
for s in stalls:
    print("  stall:", s)
if not stalls:
    print("VERDICT: NO STALLS — fix effective")
elif len(stalls) == 1:
    print("VERDICT: single residual stall (old-TTL entry) then silence — fix likely effective")
else:
    print("VERDICT: repeated stalls — fix NOT effective, investigate")
