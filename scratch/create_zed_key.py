"""Create a dedicated Zed API key in OmniRoute + verify it authenticates on /v1.
Prints the plaintext key ONCE to stdout (for the user). Never writes it to any file.
"""
import json, sys, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
for a in range(5):
    try:
        s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45); break
    except Exception as e:
        print(f"login retry {a+1}: {type(e).__name__}"); time.sleep(10)

# 1. list existing keys (masked) to avoid duplicates
r = s.get(f"{BASE}/api/keys", timeout=30)
existing = r.json().get("keys", []) if r.status_code == 200 else []
print("existing keys:", [(k.get("name"), k.get("key"), k.get("isActive")) for k in existing])

zed_keys = [k for k in existing if k.get("name") == "zed-editor" and k.get("isActive")]

# 2. create a fresh dedicated key
r = s.post(f"{BASE}/api/keys", json={"name": "zed-editor"}, timeout=30)
print(f"\nPOST /api/keys -> {r.status_code}")
print(r.text[:500])
if r.status_code not in (200, 201):
    sys.exit("key creation failed")
j = r.json()
# find the plaintext key field
plain = j.get("key") or j.get("apiKey") or j.get("plaintext") or (j.get("data") or {}).get("key")
if not plain:
    # search nested
    def find_key(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and v.startswith("sk-") and "****" not in v and len(v) > 20:
                    return v
                f = find_key(v)
                if f: return f
        elif isinstance(o, list):
            for v in o:
                f = find_key(v)
                if f: return f
        return None
    plain = find_key(j)

if not plain:
    sys.exit("could not locate plaintext key in response")

# 3. verify the new key authenticates on /v1
body = {"model": "auto/best-coding",
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "max_tokens": 8, "stream": False}
r2 = requests.post(f"{BASE}/v1/chat/completions", json=body, timeout=90,
                   headers={"Authorization": f"Bearer {plain}"})
print(f"\nverify with new key -> {r2.status_code}")

print("\n=== CREDENTIALS FOR ZED ===")
print(f"BASE_URL = {BASE}/v1")
print(f"API_KEY  = {plain}")
print(f"verified = {r2.status_code == 200}")
