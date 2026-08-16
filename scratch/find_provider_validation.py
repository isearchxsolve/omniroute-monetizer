#!/usr/bin/env python3
"""Find POST /api/providers validation logic in OmniRoute dist."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

hits = []
for root, dirs, files in os.walk(DIST):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        fp = os.path.join(root, fn)
        try:
            t = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        if "Invalid provider" in t:
            hits.append((fp, t))

print(f"files containing 'Invalid provider': {len(hits)}")
for fp, t in hits:
    print("\n===", fp)
    for m in re.finditer(r"Invalid provider", t):
        s = max(0, m.start() - 1200)
        e = min(len(t), m.end() + 400)
        print(t[s:e].replace("\n", " ")[:1800])
        print("-----")
