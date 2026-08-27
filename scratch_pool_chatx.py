import sys, pathlib
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from session_pool import SessionPool, _client_for

pool = SessionPool()
# find chatx session
cx = [s for s in pool.sessions if "chatx" in s.host]
print("chatx sessions:", [(s.key, s.dispatchable, s.client_cls.__name__ if s.client_cls else None) for s in cx])
for s in cx:
    print("  client_cls:", s.client_cls.__name__ if s.client_cls else None)
    if s.dispatchable:
        out = s.chat([{"role": "user", "content": "Reply exactly one word: Omni."}])
        print("  LIVE via pool ->", repr(out.get("text", "")[:120]), "| label:", out.get("label"))
