"""Probe /api/jobs to see if the credential-health sweep is a registered job
that can be disabled at runtime (no restart needed)."""
import os
import requests

BASE = "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "<REDACTED>")

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": PASSWORD}, timeout=10)
print("login:", r.status_code)
if r.status_code != 200:
    raise SystemExit("login failed")

r = s.get(f"{BASE}/api/jobs", timeout=10)
print("GET /api/jobs:", r.status_code)
if r.status_code == 200:
    import json
    data = r.json()
    print(json.dumps(data, indent=2)[:4000])
