#!/usr/bin/env python3
"""Scan ALL sandbox chunks for every occurrence of modelCatalogCacheTtlMs to
find both the schema definitions (3 known) and the runtime CONSUMPTION site(s)
that actually read the TTL and configure the model-catalog cache."""
import os
import sys

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
KEY = "modelCatalogCacheTtlMs"

hits = []
n = 0
for root, _dirs, files in os.walk(CHUNK_DIR):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        n += 1
        p = os.path.join(root, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except Exception:
            continue
        if KEY in data:
            # collect offsets
            offs = []
            idx = 0
            while True:
                idx = data.find(KEY, idx)
                if idx == -1:
                    break
                offs.append(idx)
                idx += len(KEY)
            hits.append((fn, len(data), offs))

print(f"scanned {n} .js files")
print(f"files containing '{KEY}': {len(hits)}")
print("=" * 70)
for fn, ln, offs in hits:
    print(f"{fn}  (len={ln}, occurrences={len(offs)}, offsets={offs})")
