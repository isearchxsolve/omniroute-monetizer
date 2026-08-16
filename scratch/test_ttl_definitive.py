#!/usr/bin/env python3
"""DEFINITIVE TTL-honored test, accounting for the 30s stale-while-revalidate window.

Cache entry: expiresAt = populate_time + TTL.
Stale-while-revalidate: if now - expiresAt <= 30000, return stale entry fast.

Test: set TTL=5000, populate cache, wait 35s.
  - If TTL HONORED (5000): entry expired at +5s; at +35s, 35s-5s=30s >= 30s window
    boundary -> genuine MISS -> SLOW rebuild (~1.5s+).
  - If TTL CLAMPED to 60000: entry valid until +60s; at +35s still valid -> fast HIT.

We use 40s wait to be safely beyond the 30s stale window.
"""
import time
import requests

BASE = "http://127.0.0.1:20199"
s = requests.Session()

def login():
    r = s.post(BASE + "/api/auth/login", json={"password": "sandbox-test-password-2026"}, timeout=60)
    print("login:", r.status_code)

def set_ttl(ms):
    r = s.put(BASE + "/api/settings/cache-config",
              json={"modelCatalogCacheTtlMs": ms}, timeout=60)
    print(f"PUT TTL={ms}: {r.status_code} {r.text[:100]}")

def get_ttl():
    r = s.get(BASE + "/api/settings/cache-config", timeout=60)
    return r.json().get("modelCatalogCacheTtlMs")

def catalog(label):
    t0 = time.time()
    r = s.get(BASE + "/api/models/catalog", timeout=180)
    dt = time.time() - t0
    print(f"  [{label}] catalog: {r.status_code} in {dt:.3f}s")
    return dt

login()

print("\n=== Set TTL to 5000ms ===")
set_ttl(5000)
print("readback TTL:", get_ttl())

print("\n=== Populate cache (MISS, slow) ===")
t_pop = catalog("populate")

print("\n=== Immediate re-request (HIT, fast) ===")
catalog("immediate-hit")

print("\n=== Wait 40s (beyond 5s TTL + 30s stale window) ===")
time.sleep(40)

print("=== Request after 40s ===")
t_after = catalog("after-40s")

print("\n=== VERDICT ===")
if t_after > 0.5:
    print(f"SLOW ({t_after:.3f}s) -> TTL=5000 was HONORED. Runtime reads raw DB TTL. Hotfix clamp is INERT.")
else:
    print(f"FAST ({t_after:.3f}s) -> TTL NOT honored (still cached/clamped at 60s). Investigate further.")

print("\n=== Restore TTL to 600000 ===")
set_ttl(600000)
print("readback TTL:", get_ttl())
print("DONE")
