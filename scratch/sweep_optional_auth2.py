#!/usr/bin/env python3
"""Extract all OmniRoute providers with authType optional/none from dist.
Uses os.walk (glob skips the .build dot-directory).
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

pat = re.compile(r'authType:"(optional|none)"')
id_pat = re.compile(r'id:"([a-z0-9\-]+)"')
found = {}
scanned = 0

for root, dirs, files in os.walk(DIST):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        fp = os.path.join(root, fn)
        scanned += 1
        try:
            with open(fp, encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            continue
        for m in pat.finditer(text):
            start = max(0, m.start() - 2500)
            chunk = text[start:m.start()]
            ids = id_pat.findall(chunk)
            if ids:
                found[ids[-1]] = m.group(1)

print(f"scanned {scanned} js files")
print(f"providers with authType optional/none: {len(found)}")
for pid in sorted(found):
    print(f"  {pid} -> {found[pid]}")
