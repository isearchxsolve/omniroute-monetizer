#!/usr/bin/env python3
"""Find the chunk defining Turbopack module 167213 (getDatabaseSettings source)."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
TARGET = "167213"

for root, _dirs, files in os.walk(CHUNK_DIR):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(200)
        except Exception:
            continue
        if head.startswith(f"module.exports=[{TARGET},"):
            print(f"FOUND: {p}")
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            print(f"length: {len(data)}")
            # dump getDatabaseSettings occurrences
            idxs = [m.start() for m in re.finditer(r"getDatabaseSettings", data)]
            print(f"getDatabaseSettings occurrences: {len(idxs)}")
            for i in idxs:
                print(f"\n--- @ {i} ---")
                print(data[max(0, i-200):i+800])
