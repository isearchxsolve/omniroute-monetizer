#!/usr/bin/env python3
"""Find the runtime CONSUMPTION site of modelCatalogCacheTtlMs by searching for
property-access patterns (`.modelCatalogCacheTtlMs`) as opposed to schema
definitions (`modelCatalogCacheTtlMs:z.number`) or field-map entries
(`modelCatalogCacheTtlMs:["..."]`)."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
KEY = "modelCatalogCacheTtlMs"

# property access: something.modelCatalogCacheTtlMs  (a dot immediately before)
ACCESS_RE = re.compile(r"\." + re.escape(KEY))

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
        offs = [m.start() for m in ACCESS_RE.finditer(data)]
        if offs:
            hits.append((fn, len(data), offs, data))

print(f"scanned {n} files; files with '.{KEY}' property-access: {len(hits)}")
print("=" * 70)
# Dedupe by context signature to avoid 100 identical route-chunk copies
seen_ctx = set()
for fn, ln, offs, data in hits:
    for off in offs:
        start = max(0, off - 200)
        end = min(len(data), off + 160)
        ctx = data[start:end]
        sig = ctx
        if sig in seen_ctx:
            continue
        seen_ctx.add(sig)
        print(f"\n### {fn} @ {off} (len={ln})")
        print(ctx)
        print("-" * 40)
