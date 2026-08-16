"""Test openrouter connection via OmniRoute's own test endpoint + probe account state."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)

OR_ID = "49aa144d-9005-4968-a6cd-a36e8a2e947f"

# 1. OmniRoute's own connection test
for method in ["POST", "GET"]:
    r = s.request(method, f"{BASE}/api/providers/{OR_ID}/test", timeout=60)
    print(f"{method} /test: {r.status_code} {r.text[:400]}")
    if r.status_code != 404:
        break

# 2. probe account-related endpoints
for path in [f"/api/providers/{OR_ID}/accounts", "/api/accounts", f"/api/providers/{OR_ID}"]:
    try:
        r = s.get(BASE + path, timeout=15)
        body = r.text[:500]
        print(f"\nGET {path}: {r.status_code}")
        print(body)
    except Exception as e:
        print(f"\nGET {path}: ERR {e}")
