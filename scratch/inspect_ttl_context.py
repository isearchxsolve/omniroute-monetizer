#!/usr/bin/env python3
"""Extract context around modelCatalogCacheTtlMs in the sandbox chunks to
determine which settings object/schema it belongs to and how it is set."""
import re
import sys

CHUNKS = [
    r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks\src_shared_0p0h6qs._.js",
    r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks\src_shared_1mmftfa._.js",
    r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks\src_shared_1z-n08e._.js",
]

KEY = "modelCatalogCacheTtlMs"

for path in CHUNKS:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = f.read()
    print(f"\n{'='*70}\n{path.split(chr(92))[-1]}  (len={len(data)})")
    for m in re.finditer(re.escape(KEY), data):
        start = max(0, m.start() - 400)
        end = min(len(data), m.end() + 200)
        ctx = data[start:end]
        print(f"\n--- offset {m.start()} ---")
        print(ctx)
        print("---")
