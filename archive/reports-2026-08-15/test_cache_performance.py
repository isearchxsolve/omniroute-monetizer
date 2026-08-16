#!/usr/bin/env python3
"""Test model cache performance when using omniroute_api.py client."""

import sys
sys.path.insert(0, 'scripts/automation')

import time
from pathlib import Path
from omniroute_api import OmniRouteAPI

print("=== Test 1: First call (should be slow, cache miss) ===")
api = OmniRouteAPI()
t1 = time.time()
models1 = api.list_models()
t2 = time.time()
elapsed1 = t2 - t1
print(f"First call: {elapsed1:.2f}s, models: {len(models1) if models1 else 0}")

print("\n=== Test 2: Immediate second call (should be fast, cache hit) ===")
t3 = time.time()
models2 = api.list_models()
t4 = time.time()
elapsed2 = t4 - t3
print(f"Second call: {elapsed2:.2f}s, models: {len(models2) if models2 else 0}")

if elapsed2 < 1.0:
    print(f"✅ CACHE WORKING: {elapsed2:.2f}s < 1.0s")
else:
    print(f"❌ CACHE NOT WORKING: {elapsed2:.2f}s >= 1.0s")

print("\n=== Test 3: Check cache file ===")
cache_file = Path("state/model_cache.json")
if cache_file.exists():
    print(f"✅ Cache file exists: {cache_file}")
    import json
    with open(cache_file) as f:
        cache_data = json.load(f)
    print(f"Cache contains: {len(cache_data.get('models', []))} models")
    print(f"Cache TTL expires: {cache_data.get('expires_at', 'N/A')}")
else:
    print(f"❌ Cache file not found: {cache_file}")

print("\n=== Test 4: Third call after 2s (should still be cached) ===")
time.sleep(2)
t5 = time.time()
models3 = api.list_models()
t6 = time.time()
elapsed3 = t6 - t5
print(f"Third call: {elapsed3:.2f}s, models: {len(models3) if models3 else 0}")

print(f"\nSummary:")
print(f"  First:  {elapsed1:.2f}s (cache miss)")
print(f"  Second: {elapsed2:.2f}s (cache hit)")
print(f"  Third:  {elapsed3:.2f}s (cache hit)")
print(f"  Improvement: {(elapsed1 - elapsed2):.2f}s ({((elapsed1 - elapsed2)/elapsed1 * 100):.0f}%)")
