"""Inspect the catalog cache implementation chunk for TTL usage and invalidation paths.
Goal: determine whether the cache is ONLY expired by TTL, or also invalidated by
timers/events (which would make a TTL raise ineffective)."""
import re, os

CHUNK = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\_1zepxms._.js"

src = open(CHUNK, encoding="utf-8", errors="replace").read()
print("chunk size:", len(src))

# 1. Show context around every modelCatalogCacheTtlMs occurrence
for m in re.finditer(r"modelCatalogCacheTtlMs", src):
    s = max(0, m.start() - 300)
    e = min(len(src), m.end() + 300)
    print("\n===== TTL occurrence @", m.start(), "=====")
    print(src[s:e])

# 2. Look for cache invalidation / delete / clear patterns near catalog code
print("\n\n===== invalidation-ish patterns =====")
for pat in [r"\.delete\(", r"\.clear\(\)", r"invalidat", r"evict", r"expire", r"Date\.now\(\)\s*[-+]", r"setTimeout\(", r"setInterval\("]:
    hits = list(re.finditer(pat, src))
    print(f"\n--- {pat}: {len(hits)} hits ---")
    for m in hits[:8]:
        s = max(0, m.start() - 150)
        e = min(len(src), m.end() + 150)
        print("  @", m.start(), ":", src[s:e].replace("\n", " ")[:320])
