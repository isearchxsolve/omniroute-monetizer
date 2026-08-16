#!/usr/bin/env python3
"""Focused scan of the 5 catalog-service chunks for getCatalogDiagnosticsHeaders
implementation and any header that exposes the effective TTL."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
TARGETS = ["_0dfofzt._.js", "_10gz1jg._.js", "_17s8hnj._.js", "_1gqxt8d._.js", "_1ptnbf9._.js"]

for fn in TARGETS:
    p = os.path.join(CHUNK_DIR, fn)
    if not os.path.exists(p):
        print(f"MISSING {fn}")
        continue
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        data = f.read()
    # find getCatalogDiagnosticsHeaders occurrences
    idxs = [m.start() for m in re.finditer(r"getCatalogDiagnosticsHeaders", data)]
    print(f"\n{'='*70}\n{fn}: {len(idxs)} occurrences of getCatalogDiagnosticsHeaders")
    for i in idxs:
        print(f"  --- @ {i} ---")
        print("  " + data[max(0, i-80):i+400].replace("\n", "\n  "))
