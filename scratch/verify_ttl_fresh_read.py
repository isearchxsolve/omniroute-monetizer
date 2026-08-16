#!/usr/bin/env python3
"""Verify the runtime reads TTL fresh per-request (not cached at startup).
Examine the resolveCachedCatalogResponse flow: does it call getDatabaseSettings()
on every request, and does it use cacheTTL to compute expiresAt?"""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
# The runtime consumer chunk
P = os.path.join(CHUNK_DIR, "_0dfofzt._.js")
with open(P, "r", encoding="utf-8", errors="replace") as f:
    data = f.read()

print(f"file length: {len(data)}")

# 1) find resolveCachedCatalogResponse and the cache-set with expiresAt
print("\n=== expiresAt / cacheTTL usage ===")
for m in re.finditer(r"expiresAt", data):
    i = m.start()
    print(f"  @ {i}: " + data[max(0,i-120):i+120].replace("\n"," "))

# 2) find where cacheTTL is used to set expiry
print("\n=== cacheTTL assignment/consumption ===")
for m in re.finditer(r"cacheTTL", data):
    i = m.start()
    print(f"  @ {i}: " + data[max(0,i-100):i+100].replace("\n"," "))

# 3) find the isStale / expiry check
print("\n=== stale/expiry checks ===")
for pat in [r"Date\.now\(\)\s*[><=]", r"isStale", r"staleWhileRevalidate", r"STALE_WHILE"]:
    for m in re.finditer(pat, data):
        i = m.start()
        print(f"  [{pat}] @ {i}: " + data[max(0,i-80):i+80].replace("\n"," "))
