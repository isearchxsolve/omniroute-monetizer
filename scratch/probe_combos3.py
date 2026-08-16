"""Dump raw combos response. Read-only."""
import json
import os

import requests

BASE = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if BASE.endswith("/v1"):
    BASE = BASE[:-3]
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "<REDACTED>")

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": PASSWORD}, timeout=15)
assert r.status_code == 200

r = s.get(f"{BASE}/api/combos", timeout=15)
raw = r.text
path = os.path.join(os.path.dirname(__file__), "probe_combos_raw.json")
with open(path, "w", encoding="utf-8") as f:
    f.write(raw)
print("WROTE", path, "bytes:", len(raw))
