import sys, pathlib, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(r"d:\omniroute-monetizer\scripts\automation")))
import session_pool as sp

pool = sp.SessionPool()

# Trace every pick() call and every per-session chat attempt.
orig_pick = pool.pick
picks = []
def traced_pick(now, modality=None, host=None):
    s = orig_pick(now, modality, host)
    picks.append(s.key if s else None)
    print(f"  pick -> {s.key if s else 'None'}")
    return s
pool.pick = traced_pick

print("=== pool.chat() trace (modality=chat) ===")
print(f"live chat sessions: {len(pool.live('chat'))}")
t0 = time.time()
try:
    r = pool.chat([{"role": "user", "content": "Reply exactly one word: Omni"}], modality="chat")
    print(f"\nSUCCESS after {time.time()-t0:.1f}s via {r.get('provider')} label={r.get('label')}")
    print(f"text={ (r.get('text') or '')[:80]!r}")
except Exception as e:
    print(f"\nFAILED after {time.time()-t0:.1f}s: {type(e).__name__}: {e}")
print(f"\nsessions attempted (pick order): {len(picks)}")
for i, k in enumerate(picks, 1):
    print(f"  {i:2d}. {k}")
