#!/usr/bin/env python3
"""Debug: find which dist files contain authType strings at all."""
import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"
needle = 'authType:"optional"'
hits = []
n = 0
for fp in glob.glob(os.path.join(DIST, "**", "*.js"), recursive=True):
    n += 1
    try:
        with open(fp, encoding="utf-8", errors="ignore") as f:
            t = f.read()
    except Exception:
        continue
    if needle in t:
        hits.append((fp, t.count(needle), len(t)))

print(f"scanned {n} files")
print(f"files containing {needle!r}: {len(hits)}")
for fp, c, size in hits:
    print(f"  {os.path.basename(fp)}: {c} hits, {size//1024} KB")
