import sys, pathlib, json, time, urllib.request, urllib.error
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(r"d:\omniroute-monetizer\scripts\automation")))

# 1) Raw HTTP call to capture the 500 body
print("=== RAW HTTP CALL (capture error body) ===")
req = urllib.request.Request(
    "http://127.0.0.1:8190/v1/chat/completions",
    data=json.dumps({"model": "session-pool/auto",
                     "messages": [{"role": "user", "content": "Reply exactly one word: Omni"}]}).encode(),
    headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print("HTTP", r.status)
        print(r.read().decode()[:500])
except urllib.error.HTTPError as e:
    print("HTTPError", e.code)
    print(e.read().decode()[:500])
except Exception as e:
    print("EXC", type(e).__name__, e)

# 2) Pool state
print("\n=== POOL LIVE CHAT SESSIONS ===")
import session_pool as sp
pool = sp.SessionPool()
now = time.time()
chat = pool.live(modality="chat")
print(f"live chat sessions: {len(chat)}")
for s in sorted(chat, key=lambda x: x.last_used):
    cool = "COOLING" if s.cooldown_until > now else "ready"
    print(f"  {s.host:26s} dead={s.dead!s:5s} {cool:8s} last_used={s.last_used:.0f} "
          f"err={s.last_error or '-'}")
