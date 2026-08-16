"""Post-restart: is openrouter still 'unavailable'? Test an openrouter-routed model directly."""
import json
import sys
import time

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)

# 1. Are there 'accounts unavailable' lines AFTER the restart (13:41 UTC)?
LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

post = []
for l in lines[-1500:]:
    if "accounts unavailable" in l or "No active credentials" in l:
        try:
            j = json.loads(l)
            post.append((j.get("time", ""), (j.get("msg") or "")[:120]))
        except Exception:
            pass
print("=== 'unavailable' lines in last 1500 (chronological) ===")
for t, m in post[-10:]:
    print(f"[{t}] {m}")

# 2. Force-route a request to an openrouter model
print("\n=== direct openrouter model test ===")
payload = {
    "model": "openrouter/moonshotai/kimi-k3",
    "messages": [{"role": "user", "content": "Reply with the single word: pong"}],
    "max_tokens": 20,
    "stream": False,
}
t0 = time.time()
r = s.post(f"{BASE}/v1/chat/completions", json=payload, timeout=60)
dt = time.time() - t0
print(f"openrouter/moonshotai/kimi-k3: HTTP {r.status_code} in {dt:.1f}s")
print(r.text[:400])
