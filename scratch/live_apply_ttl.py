"""LIVE Stage 3 (revised): raise modelCatalogCacheTtlMs via the CORRECT endpoint
/api/settings/cache-config. Backup-first, then apply, then readback-verify.

T11-safe: password from OMNIROUTE_PASSWORD env (in-script fallback), never printed.
Backup contains only cache-config settings (no secrets).

Why no restart: Stage 1 proved the runtime reads getDatabaseSettings().cache raw
per-request (no Zod parse, clamp is dead code), so the new TTL takes effect on the
next catalog request.
"""
import os
import json
import datetime
import sys
import requests

BASE = "http://localhost:20128"
NEW_TTL = 600000  # 10 min — the exact value validated end-to-end in sandbox
BACKUP = os.path.join("d:\\omniroute-monetizer", "state",
                      "live_cache_config_backup_" +
                      datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".json")

pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip() or "<REDACTED>"

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": pw}, timeout=15)
print("login:", r.status_code)
if r.status_code not in (200, 204):
    print("LOGIN FAILED — aborting, live untouched")
    sys.exit(1)

# 1) BACKUP current cache-config
r = s.get(f"{BASE}/api/settings/cache-config", timeout=15)
print("GET cache-config:", r.status_code)
if r.status_code != 200:
    print("GET failed — aborting, live untouched")
    sys.exit(1)
before = r.json()
print("BEFORE:", json.dumps(before, indent=2))
os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
with open(BACKUP, "w", encoding="utf-8") as f:
    json.dump(before, f, indent=2)
print("backup written:", BACKUP)

# 2) APPLY new TTL
r = s.put(f"{BASE}/api/settings/cache-config",
          json={"modelCatalogCacheTtlMs": NEW_TTL}, timeout=15)
print(f"PUT modelCatalogCacheTtlMs={NEW_TTL}:", r.status_code, r.text[:150])
if r.status_code not in (200, 204):
    print("PUT failed — live unchanged")
    sys.exit(1)

# 3) READBACK verify
r = s.get(f"{BASE}/api/settings/cache-config", timeout=15)
after = r.json()
print("AFTER:", json.dumps(after, indent=2))
got = after.get("modelCatalogCacheTtlMs")
if got == NEW_TTL:
    print(f"\nSUCCESS: live modelCatalogCacheTtlMs is now {got}")
else:
    print(f"\nMISMATCH: expected {NEW_TTL}, got {got}")
    sys.exit(1)
