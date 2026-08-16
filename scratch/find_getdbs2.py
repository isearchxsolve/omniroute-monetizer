#!/usr/bin/env python3
"""Locate the getDatabaseSettings definition via export/assignment patterns,
then dump its body to see if it Zod-parses on read."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
KEY = "getDatabaseSettings"

# assignment/export forms
ASSIGN_RE = re.compile(re.escape(KEY) + r"\s*[:=]")

found = []
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
            found.append((fn, m.start(), data))

print(f"assignment/export occurrences of '{KEY}': {len(found)}")
print("=" * 70)
seen = set()
for fn, off, data in found:
    start = max(0, off - 120)
    end = min(len(data), off + 600)
    ctx = data[start:end]
    if ctx in seen:
        continue
    seen.add(ctx)
    print(f"\n### {fn} @ {off}")
    print(ctx)
    print("-" * 50)
    if len(seen) >= 8:
        break
