#!/usr/bin/env python3
"""Find the cache-config GET handler chunk and confirm which read function it uses.
Search for the distinctive field idempotencyWindowMs near a GET/response construction."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
KEY = "idempotencyWindowMs"

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
        if KEY in data:
            idxs = [m.start() for m in re.finditer(re.escape(KEY), data)]
            hits.append((fn, len(data), idxs, data))

print(f"files with '{KEY}': {len(hits)}")
for fn, ln, idxs, data in hits:
    print(f"\n{'='*70}\n{fn} (len={ln}, {len(idxs)} occ)")
    for i in idxs[:4]:
        print(f"  --- @ {i} ---")
        print("  " + data[max(0, i-350):i+250].replace("\n", "\n  "))
