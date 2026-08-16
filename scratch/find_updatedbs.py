#!/usr/bin/env python3
"""Find updateDatabaseSettings definition + check whether the settings DB layer
applies Zod parse/safeParse anywhere (which would enforce the TTL clamp)."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

# 1) find updateDatabaseSettings assignments
ASSIGN_RE = re.compile(r"updateDatabaseSettings\s*[:=]")
# 2) find CATALOG_CACHE_TTL_MS_DEFAULT definition
DEFAULT_RE = re.compile(r"CATALOG_CACHE_TTL_MS_DEFAULT\s*[:=]")

assign_hits = []
default_hits = []
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
        for m in ASSIGN_RE.finditer(data):
            assign_hits.append((fn, m.start(), data))
        for m in DEFAULT_RE.finditer(data):
            default_hits.append((fn, m.start(), data))

print(f"updateDatabaseSettings assignments: {len(assign_hits)}")
seen = set()
for fn, off, data in assign_hits:
    start = max(0, off - 100)
    end = min(len(data), off + 700)
    ctx = data[start:end]
    if ctx in seen:
        continue
    seen.add(ctx)
    print(f"\n### updateDatabaseSettings in {fn} @ {off}")
    print(ctx)
    print("-" * 50)
    if len(seen) >= 5:
        break

print(f"\n\nCATALOG_CACHE_TTL_MS_DEFAULT definitions: {len(default_hits)}")
seen2 = set()
for fn, off, data in default_hits:
    start = max(0, off - 100)
    end = min(len(data), off + 200)
    ctx = data[start:end]
    if ctx in seen2:
        continue
    seen2.add(ctx)
    print(f"\n### DEFAULT in {fn} @ {off}")
    print(ctx)
    print("-" * 50)
    if len(seen2) >= 5:
        break
