"""Prove concurrent pool.chat() calls never double-book a session (worklog #1110).

Fires N threads at pool.chat() simultaneously with stubbed clients. Before the
reserve() fix, all threads read the same LRU head and queued on one host.
After: each concurrent caller must land on a DISTINCT session.
"""
import sys, pathlib, time, threading
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import session_pool as sp

pool = sp.SessionPool()
live = pool.live(modality="chat")
print(f"live chat sessions: {len(live)}")

# Stub every live chat session with a client that records which host served.
served = []
slock = threading.Lock()

class Stub:
    def __init__(self, host):
        self.host = host
    def chat(self, messages, model=None, **kw):
        with slock:
            served.append(self.host)
        time.sleep(0.05)  # small hold so overlap is real
        return {"text": f"ok-{self.host}", "label": self.host}

for s in live:
    s._client = Stub(s.host)
    s.dead = False
    s.cooldown_until = 0.0
    s.last_used = 0.0

N = min(8, len(live))
results = [None] * N
def worker(i):
    try:
        results[i] = pool.chat([{"role": "user", "content": "hi"}], modality="chat")
    except Exception as e:
        results[i] = {"error": str(e)}

threads = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
t0 = time.time()
for t in threads: t.start()
for t in threads: t.join()
dt = time.time() - t0

hosts = [r.get("provider") for r in results if r and "provider" in r]
errs = [r for r in results if r and "error" in r]
print(f"\nfired {N} CONCURRENT calls in {dt:.2f}s")
print(f"  served by hosts: {hosts}")
print(f"  distinct hosts:  {len(set(hosts))}")
print(f"  errors: {len(errs)}")
if errs:
    for e in errs[:3]:
        print("   ", e["error"][:120])

if len(set(hosts)) == N and not errs:
    print("VERDICT: NO_DOUBLE_BOOKING -- every concurrent call hit a DISTINCT session")
elif len(set(hosts)) > 1:
    print(f"VERDICT: PARTIAL -- {len(set(hosts))}/{N} distinct (some overlap)")
else:
    print("VERDICT: BROKEN -- concurrent calls collapsed onto one session")
