#!/usr/bin/env python3
"""DECISIVE EMPIRICAL TEST: does the runtime honor the raw DB TTL value?

Strategy: set modelCatalogCacheTtlMs to a SHORT value (5000ms), then observe the
model-catalog cache expire after >5s. If the TTL were clamped to 60000 regardless,
a request after 6s would still be a cache HIT. If the TTL is honored, it's a MISS.

We track /api/cache/stats (hits/misses/size) across catalog requests.
"""
import time
import requests

BASE = "http://127.0.0.1:20199"
s = requests.Session()

def login():
    r = s.post(BASE + "/api/auth/login", json={"password": "sandbox-test-password-2026"}, timeout=60)
    print("login:", r.status_code)

def cache_stats():
    r = s.get(BASE + "/api/cache/stats", timeout=60)
    try:
        return r.json()
    except Exception:
        return {"raw": r.text[:200]}

def set_ttl(ms):
    r = s.put(BASE + "/api/settings/cache-config",
              json={"modelCatalogCacheTtlMs": ms}, timeout=60)
    print(f"PUT TTL={ms}: {r.status_code} {r.text[:120]}")

def get_ttl():
    r = s.get(BASE + "/api/settings/cache-config", timeout=60)
    return r.json().get("modelCatalogCacheTtlMs")

def catalog():
    t0 = time.time()
    r = s.get(BASE + "/api/models/catalog", timeout=180)
    dt = time.time() - t0
    return r.status_code, dt

login()

print("\n=== baseline cache stats ===")
print(cache_stats())

print("\n=== STEP 1: set TTL to 5000ms (5s) ===")
set_ttl(5000)
print("readback TTL:", get_ttl())

print("\n=== STEP 2: first catalog request (expect MISS, populates cache) ===")
st, dt = catalog()
print(f"catalog: {st} in {dt:.3f}s")
print("stats:", cache_stats())

print("\n=== STEP 3: immediate second catalog request (expect HIT) ===")
st, dt = catalog()
print(f"catalog: {st} in {dt:.3f}s")
print("stats:", cache_stats())

print("\n=== STEP 4: wait 7s (> 5s TTL), then request (expect MISS if TTL honored) ===")
time.sleep(7)
st, dt = catalog()
print(f"catalog: {st} in {dt:.3f}s")
print("stats:", cache_stats())

print("\n=== STEP 5: restore TTL to 600000 (10 min) ===")
set_ttl(600000)
print("readback TTL:", get_ttl())
print("\nDONE")
