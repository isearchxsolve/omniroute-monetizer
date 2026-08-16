"""Re-test openrouter routing NOW (after connection test refreshed state) + overall health."""
import sys
import time

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)

# health
h = s.get(f"{BASE}/api/monitoring/health", timeout=15).json()
print(f"health: status={h.get('status')} uptime={h.get('uptime', 0):.0f}s activeConns={h.get('activeConnections')}")

# openrouter direct models (use real openrouter model ids)
tests = [
    "openrouter/moonshotai/kimi-k3",
    "openrouter/z-ai/glm-4.5-air",
    "openrouter/openai/gpt-4o-mini",
]
payload = {"messages": [{"role": "user", "content": "Reply with one word: pong"}], "max_tokens": 15, "stream": False}
for m in tests:
    payload["model"] = m
    t0 = time.time()
    try:
        r = s.post(f"{BASE}/v1/chat/completions", json=payload, timeout=60)
        dt = time.time() - t0
        if r.status_code == 200:
            c = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
            print(f"OK   {m:40s} {dt:5.1f}s content={c[:30]!r}")
        else:
            print(f"FAIL {m:40s} {dt:5.1f}s HTTP {r.status_code}: {r.text[:160]}")
    except Exception as e:
        print(f"ERR  {m:40s} {time.time()-t0:5.1f}s {type(e).__name__}: {str(e)[:120]}")
