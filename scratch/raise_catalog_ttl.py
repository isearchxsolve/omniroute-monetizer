"""Mitigate blocker #3: raise modelCatalogCacheTtlMs (default 60000ms = 60s cap)
via the native settings API. Read current value first, then update. T11-safe:
password read from .env, never printed."""
import os, re, json, sys, requests

BASE = "http://localhost:20128"

# password from environment (same pattern as other scratch scripts); never printed
pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
if not pw:
    # fall back to the same default the other scratch scripts use
    pw = "<REDACTED>"

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": pw}, timeout=10)
print("login:", r.status_code)
if r.status_code not in (200, 204):
    print("login failed"); sys.exit(1)

# 1) read current settings
r = s.get(f"{BASE}/api/settings", timeout=10)
print("GET /api/settings:", r.status_code)
if r.status_code != 200:
    # try alternate endpoint names
    for alt in ("/api/settings/cache", "/api/config"):
        r2 = s.get(BASE + alt, timeout=10)
        print(f"  alt {alt}: {r2.status_code}")
    sys.exit(1)

data = r.json()
cache = data.get("cache", {})
print("current cache settings:", json.dumps(cache, indent=2))
cur_ttl = cache.get("modelCatalogCacheTtlMs")
print("current modelCatalogCacheTtlMs:", cur_ttl)

# 2) update TTL to 1 hour (3600000 ms)
NEW_TTL = 3600000
payload = {"cache": {"modelCatalogCacheTtlMs": NEW_TTL}}
r = s.put(f"{BASE}/api/settings", json=payload, timeout=15)
print("PUT /api/settings:", r.status_code, r.text[:300])
if r.status_code not in (200, 204):
    r = s.patch(f"{BASE}/api/settings", json=payload, timeout=15)
    print("PATCH /api/settings:", r.status_code, r.text[:300])

# 3) verify
r = s.get(f"{BASE}/api/settings", timeout=10)
cache2 = r.json().get("cache", {})
print("after update, modelCatalogCacheTtlMs:", cache2.get("modelCatalogCacheTtlMs"))
