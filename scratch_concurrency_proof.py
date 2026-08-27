"""CONCURRENCY PROOF: fire N parallel chat calls at graduated (stateless-replay)
seats and show they run CONCURRENTLY (wall-clock ~= slowest single call), not
serialized behind the Chrome driver lock (which would be ~= sum of calls).
This is the exact anti-pattern the operator flagged."""
import sys, json, pathlib, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from session_pool import SessionPool, _client_for

pool = SessionPool()
# collect graduated stateless-replay seats
grad = []
for s in pool.sessions:
    if not s.dispatchable:
        continue
    raw = json.loads(s.path.read_text(encoding="utf-8-sig"))
    cls = _client_for(s.host, raw)
    if cls and cls.__name__ == "UniversalSessionClient":
        grad.append((s.host, str(s.path)))
print(f"graduated stateless seats available: {len(grad)}")
targets = grad[:6]
print("targets:", [h for h, _ in targets])

active = 0
peak = 0
lock = threading.Lock()
results = []

def call(host, path):
    global active, peak
    from universal_replay import UniversalSessionClient
    with lock:
        active += 1
        peak = max(peak, active)
    t0 = time.time()
    try:
        c = UniversalSessionClient(path)
        r = c.chat([{"role": "user", "content": "Reply with the single word: ready"}], model="probe")
        text = r.get("text", "") if isinstance(r, dict) else str(r)
        ok = bool(text.strip())
    except Exception as e:
        text = f"{type(e).__name__}: {str(e)[:60]}"
        ok = False
    dt = time.time() - t0
    with lock:
        active -= 1
    return host, ok, dt, text[:60]

t_start = time.time()
with ThreadPoolExecutor(max_workers=len(targets)) as ex:
    futs = [ex.submit(call, h, p) for h, p in targets]
    for f in as_completed(futs):
        host, ok, dt, text = f.result()
        results.append((host, ok, dt))
        print(f"  {'OK ' if ok else 'ERR'} {host:22} {dt:5.1f}s  {text!r}")
wall = time.time() - t_start

sums = sum(dt for _, _, dt in results)
print()
print(f"wall-clock for {len(results)} parallel calls : {wall:.1f}s")
print(f"sum if they had SERIALIZED       : {sums:.1f}s")
print(f"peak simultaneous in-flight      : {peak}")
print(f"speedup vs serialization         : {sums/wall:.1f}x")
print()
if peak >= 2 and wall < sums * 0.7:
    print("VERDICT: CONCURRENT — calls overlapped, no driver-lock serialization.")
else:
    print("VERDICT: NOT clearly concurrent.")
