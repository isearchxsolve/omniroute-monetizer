#!/usr/bin/env python3
"""Find the ACTUAL getDatabaseSettings implementation (not re-exports)."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

# actual definition patterns
PATS = [
    re.compile(r"async\s+function\s+getDatabaseSettings"),
    re.compile(r"function\s+getDatabaseSettings"),
    re.compile(r"getDatabaseSettings\s*=\s*async"),
    re.compile(r"getDatabaseSettings\s*=\s*\("),
    re.compile(r"getDatabaseSettings\s*\(\)\s*\{"),
    re.compile(r"getDatabaseSettings\s*:\s*async"),
]

hits = []
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
        for pat in PATS:
            for m in pat.finditer(data):
                hits.append((fn, m.start(), data, pat.pattern))

print(f"definition-pattern hits: {len(hits)}")
seen = set()
for fn, off, data, pat in hits:
    start = max(0, off - 60)
    end = min(len(data), off + 700)
    ctx = data[start:end]
    key = (fn, ctx[:80])
    if key in seen:
        continue
    seen.add(key)
    print(f"\n### {fn} @ {off}  [{pat}]")
    print(ctx)
    print("-" * 50)
    if len(seen) >= 10:
        break
