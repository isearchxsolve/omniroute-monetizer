"""Check OmniRoute provider/connection state — focus on openrouter and overall active count."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts")

import requests

BASE = "http://127.0.0.1:20128"

# resolve password via the keepalive helper
try:
    from oauth_keepalive import resolve_password
    pw = resolve_password()
except Exception as e:
    print("resolve_password failed:", e)
    sys.exit(1)

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": pw}, timeout=15)
print("login:", r.status_code)

r = s.get(f"{BASE}/api/providers", timeout=30)
data = r.json()
conns = data.get("connections", [])
print("total connections:", data.get("total"), "| returned:", len(conns))

active = [c for c in conns if c.get("isActive")]
print("active:", len(active))

# openrouter details
print("\n--- openrouter connections ---")
for c in conns:
    if "openrouter" in str(c.get("provider", "")).lower() or "openrouter" in str(c.get("name", "")).lower():
        key = c.get("apiKey") or ""
        print(json.dumps({
            "id": c.get("id"),
            "provider": c.get("provider"),
            "name": c.get("name"),
            "authType": c.get("authType"),
            "isActive": c.get("isActive"),
            "apiKey_len": len(key),
            "apiKey_prefix": key[:8] + "..." if key else "(empty)",
        }, indent=2))

# any active connection with empty key?
print("\n--- active connections with EMPTY apiKey ---")
for c in active:
    key = c.get("apiKey") or ""
    if not key:
        print(" ", c.get("id"), c.get("provider"), c.get("name"))

# summary by provider
from collections import Counter
cnt = Counter((c.get("provider"), c.get("isActive")) for c in conns)
print("\n--- provider x isActive counts ---")
for (p, a), n in sorted(cnt.items(), key=lambda x: str(x[0])):
    print(f"  {p} active={a}: {n}")
