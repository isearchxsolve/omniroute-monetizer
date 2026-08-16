"""Inspect the auto/best-free combo and test it with a longer timeout."""
import os
import time
import requests

BASE = "http://localhost:20128"
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "Keross@321")

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": PASSWORD}, timeout=10)
print(f"login: {r.status_code}")

# List combos, find best-free
r = s.get(f"{BASE}/api/combos", timeout=10)
print(f"combos: {r.status_code}")
combos = r.json()
items = combos if isinstance(combos, list) else combos.get("combos", combos.get("data", []))
print(f"total combos: {len(items)}")
for c in items:
    cid = c.get("id") or c.get("name")
    name = c.get("name") or c.get("id")
    if "free" in str(name).lower() or "free" in str(cid).lower():
        print(f"  FREE combo: id={cid} name={name}")
        print(f"    keys: {list(c.keys())}")
        # print targets
        for k in ("targets", "models", "cascade", "entries", "providers"):
            if k in c:
                print(f"    {k}: {c[k]}")
