"""READ-ONLY: determine /v1 auth requirement + find configured API key if any."""
import json, sys, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

body = {"model": "frontier", "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 8, "stream": False}

# 1. NO auth at all (no cookie, no key)
print("=== /v1/chat/completions with NO auth ===")
try:
    r = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=60)
    print(f"  status={r.status_code}")
    print("  ", r.text[:200])
except Exception as e:
    print("  EXC:", type(e).__name__, e)

# 2. with a dummy bearer key
print("\n=== with dummy Bearer key ===")
try:
    r = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=60,
                      headers={"Authorization": "Bearer sk-dummy-test"})
    print(f"  status={r.status_code}")
    print("  ", r.text[:200])
except Exception as e:
    print("  EXC:", type(e).__name__, e)

# 3. look for stored API keys in settings DB / env
print("\n=== search settings for proxy/apiKey config ===")
s = requests.Session()
for a in range(5):
    try:
        s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45); break
    except Exception:
        time.sleep(10)
for ep in ["/api/settings", "/api/settings/api-keys", "/api/keys", "/api/api-keys"]:
    try:
        r = s.get(f"{BASE}{ep}", timeout=30)
        print(f"  GET {ep}: {r.status_code}")
        if r.status_code == 200:
            txt = r.text
            print("    ", txt[:300])
    except Exception as e:
        print(f"  GET {ep}: EXC {type(e).__name__}")
