"""Post-fix live stall monitor v2: longer window + stall-gap analysis.
Confirms the NEW cadence (~10 min) vs the old (~94-101s).
Duration from argv[1] (seconds), default 510.
"""
import sys
import time
import datetime
import requests

BASE = "http://localhost:20128"
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 510
STALL_THRESHOLD = 3.0

start = time.time()
last_probe = 0.0
stalls = []          # (epoch, ts, dt, note)
probes = 0
while time.time() - start < DURATION:
    if time.time() - last_probe >= 2.0:
        last_probe = time.time()
        now = time.time()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        t0 = time.time()
        try:
            r = requests.get(f"{BASE}/v1/models", timeout=60)
            dt = time.time() - t0
            probes += 1
            if dt > STALL_THRESHOLD:
                stalls.append((now, ts, dt, r.status_code))
                print(f"[{ts}] STALL {dt:.2f}s status={r.status_code}", flush=True)
            else:
                print(f"[{ts}] ok {dt:.2f}s", flush=True)
        except Exception as e:
            dt = time.time() - t0
            probes += 1
            stalls.append((now, ts, dt, type(e).__name__))
            print(f"[{ts}] ERR {dt:.2f}s {type(e).__name__}", flush=True)
    time.sleep(0.2)

print(f"\nSUMMARY: {probes} probes over {DURATION}s, {len(stalls)} stalls >{STALL_THRESHOLD}s")
prev = None
for (ep, ts, dt, note) in stalls:
    gap = f" (gap {ep-prev:.0f}s since prev stall)" if prev else ""
    print(f"  stall {ts}: {dt:.2f}s {note}{gap}")
    prev = ep

big = [s for s in stalls if s[2] >= 20.0]
if not stalls:
    print("VERDICT: NO STALLS in window — fix effective, no rebuild occurred")
elif not big:
    print("VERDICT: only minor blips (<20s), no full freeze — fix effective")
else:
    gaps = [stalls[i][0]-stalls[i-1][0] for i in range(1, len(stalls)) if stalls[i][2]>=20 and stalls[i-1][2]>=20]
    if gaps and min(gaps) > 300:
        print(f"VERDICT: full freezes now {min(gaps):.0f}s+ apart (was ~94-101s) — fix effective, cadence reduced")
    else:
        print("VERDICT: full freezes still close together — investigate")
