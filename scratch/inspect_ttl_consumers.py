#!/usr/bin/env python3
"""Extract context around modelCatalogCacheTtlMs in representative consumer
chunks (non-schema) to determine whether the runtime re-validates via Zod."""
import os

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
KEY = "modelCatalogCacheTtlMs"

# representative files: lib chunk, a root-of-the-server chunk, a src_ chunk
TARGETS = [
    "src_lib_0-68-jc._.js",
    "src_01lpegw._.js",
    "src_16zh_cy._.js",
    "[root-of-the-server]__0-_6pjr._.js",
    "src_09m654j._.js",
]

for fn in TARGETS:
    p = os.path.join(CHUNK_DIR, fn)
    if not os.path.exists(p):
        print(f"MISSING: {fn}")
        continue
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        data = f.read()
    print(f"\n{'='*70}\n{fn}  (len={len(data)})")
    idx = 0
    count = 0
    while True:
        idx = data.find(KEY, idx)
        if idx == -1:
            break
        count += 1
        start = max(0, idx - 350)
        end = min(len(data), idx + 250)
        print(f"\n--- occurrence {count} @ offset {idx} ---")
        print(data[start:end])
        idx += len(KEY)
