#!/usr/bin/env python3
"""Search for literal CATALOG_CACHE_TTL_MS_DEFAULT and cacheTTL usage to find
the default object and the endpoint exposing effective TTL."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

LIT1 = "CATALOG_CACHE_TTL_MS_DEFAULT"
LIT2 = "cacheTTL"

hits1 = []
hits2 = []
for root, _dirs, files in os.walk(CHUNK_DIR):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except Exception:
            continue
        if LIT1 in data:
            hits1.append((fn, data))
        if LIT2 in data:
            hits2.append((fn, data))

print(f"files with '{LIT1}': {len(hits1)}")
for fn, data in hits1[:10]:
    idxs = [m.start() for m in re.finditer(re.escape(LIT1), data)]
    print(f"  {fn}: {len(idxs)} occurrences")
    for i in idxs[:3]:
        print("    ctx:", data[max(0, i-150):i+150].replace("\n", " "))

print(f"\nfiles with '{LIT2}': {len(hits2)}")
for fn, data in hits2[:10]:
    idxs = [m.start() for m in re.finditer(re.escape(LIT2), data)]
    print(f"  {fn}: {len(idxs)} occurrences")
    for i in idxs[:4]:
        print("    ctx:", data[max(0, i-200):i+200].replace("\n", " "))
