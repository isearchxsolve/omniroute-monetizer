"""Census of connection statuses + providerSpecificData keys for active ones."""
import json
import sys
from collections import Counter

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
from oauth_keepalive import resolve_password

BASE = "http://127.0.0.1:20128"

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45)
j = s.get(f"{BASE}/api/providers", timeout=90).json()
conns = j.get("connections", [])
print(f"total: {len(conns)}")

c = Counter((x.get("isActive"), x.get("testStatus")) for x in conns)
for k, v in c.most_common():
    print(f"  active={k[0]} testStatus={k[1]}: {v}")

print("\n--- active connections (any testStatus) ---")
for x in conns:
    if not x.get("isActive"):
        continue
    psd = x.get("providerSpecificData")
    if isinstance(psd, str):
        try:
            psd = json.loads(psd)
        except Exception:
            psd = {"_raw": str(psd)[:60]}
    keys = list(psd.keys()) if isinstance(psd, dict) else type(psd).__name__
    print(f"  {x.get('provider')} [{x.get('authType')}] status={x.get('testStatus')} psd={keys}")
