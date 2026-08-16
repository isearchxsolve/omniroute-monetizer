"""READ-ONLY: characterize GET /api/combos read consistency (3 fresh sessions)."""
import sys, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

for trial in range(3):
    s = requests.Session()
    s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45)
    rc = s.get(f"{BASE}/api/combos", timeout=45).json()
    combos = rc.get("combos", rc if isinstance(rc, list) else [])
    for c in combos:
        if c.get("name") == "auto/asian-flagships":
            print(f"trial {trial+1}: updatedAt={c.get('updatedAt')}")
            for m in c.get("models", []):
                print(f"    w={m.get('weight'):<4} {m.get('model')}")
    time.sleep(1)
