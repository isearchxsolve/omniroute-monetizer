"""Fast in-process proof: pool.chat() falls through the FULL pool on failure (worklog #1109).

Builds a SessionPool over the real seat files, then monkeypatches each session's
client so the first K raise the canonical ChatError('HTTP_ERROR','429') and the
(K+1)th succeeds. Verifies pool.chat() rotates past the failures instead of
surfacing the first 429. No real network calls -> instant.
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "scripts" / "automation"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import session_pool as sp
from veoaifree_chat_client import ChatError
from veo_session_replay import SessionExpired

pool = sp.SessionPool()
live = pool.live(modality="chat")
print(f"live chat sessions in pool: {len(live)}")
assert len(live) >= 3, "need >=3 live sessions for a meaningful fall-through test"

# Stub clients: first N_FAIL raise a 429 ChatError, then one succeeds.
N_FAIL = min(4, len(live) - 1)
calls = []

class StubClient:
    def __init__(self, idx, host):
        self.idx, self.host = idx, host
    def chat(self, messages, model=None, **kw):
        calls.append(self.host)
        if self.idx < N_FAIL:
            raise ChatError("HTTP_ERROR", "HTTP Error 429: ")
        return {"text": f"answer-from-{self.host}", "label": self.host}

# Wire stubs onto the first (N_FAIL+1) live sessions in LRU order.
order = sorted(live, key=lambda s: s.last_used)
for i, s in enumerate(order[:N_FAIL + 1]):
    s._client = StubClient(i, s.host)
    s.client_cls = lambda secret=None, _i=i, _h=s.host: StubClient(_i, _h)

# Force all cooldowns clear so pick() considers everyone.
now = time.time()
for s in pool.sessions:
    s.cooldown_until = 0.0
    s.dead = False

t0 = time.time()
try:
    r = pool.chat([{"role": "user", "content": "hi"}], modality="chat")
    dt = time.time() - t0
    print(f"\nRESULT: SUCCESS in {dt:.3f}s")
    print(f"  winning provider = {r.get('provider')}")
    print(f"  winning text     = {r.get('text')!r}")
    print(f"  sessions attempted (in order): {calls}")
    print(f"  distinct attempted: {len(set(calls))}")
    if len(calls) == N_FAIL + 1 and r.get("provider") == order[N_FAIL].host:
        print("  VERDICT: FALL_THROUGH_WORKS -- rotated past", N_FAIL, "429s to a live session")
    else:
        print("  VERDICT: UNEXPECTED -- check attempt order")
except ChatError as e:
    print(f"\nRESULT: FAILED (raised) after {len(calls)} attempts: {e}")
    print(f"  sessions attempted: {calls}")
    print("  VERDICT: STILL_BROKEN -- pool surfaced an error instead of rotating")

# Also prove SessionExpired marks dead and continues.
print("\n--- SessionExpired path ---")
calls2 = []
class ExpClient:
    def __init__(self, idx, host):
        self.idx, self.host = idx, host
    def chat(self, messages, model=None, **kw):
        calls2.append(self.host)
        if self.idx == 0:
            raise SessionExpired("AUTH", "Auth rejected")
        return {"text": f"ok-{self.host}", "label": self.host}
for s in pool.sessions:
    s.cooldown_until = 0.0
    s.dead = False
live2 = sorted(pool.live(modality="chat"), key=lambda s: s.last_used)
live2[0]._client = ExpClient(0, live2[0].host)
live2[1]._client = ExpClient(1, live2[1].host)
try:
    r2 = pool.chat([{"role": "user", "content": "hi"}], modality="chat")
    print(f"  winner={r2.get('provider')}  attempted={calls2}  first_dead={live2[0].dead}")
    print("  VERDICT:", "EXPIRED_FALLTHROUGH_WORKS" if (live2[0].dead and r2.get("provider") == live2[1].host) else "UNEXPECTED")
except ChatError as e:
    print(f"  FAILED: {e}  attempted={calls2}")
