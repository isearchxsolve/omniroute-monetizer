#!/usr/bin/env python3
"""Find the exact 'Invalid provider' 400 source in POST /api/providers."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

for root, dirs, files in os.walk(DIST):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        fp = os.path.join(root, fn)
        try:
            t = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        # exact bare error string
        for m in re.finditer(r'["\']Invalid provider["\']', t):
            s = max(0, m.start() - 1500)
            e = min(len(t), m.end() + 300)
            print("===", fp)
            print(t[s:e].replace("\n", " "))
            print("-----\n")
