#!/usr/bin/env python3
"""Find no-auth category registry object across ALL dist files."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

found = 0
for root, dirs, files in os.walk(DIST):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        fp = os.path.join(root, fn)
        if "mcp-server" in fp:
            continue
        try:
            t = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        # registry object: "no-auth":{category:"no-auth",providers:...}
        for m in re.finditer(r'["\']no-auth["\']\s*:\s*\{\s*category', t):
            s = max(0, m.start() - 50)
            e = min(len(t), m.end() + 4000)
            seg = t[s:e].replace("\n", " ")
            print("=== no-auth registry in", fp)
            print(seg[:4200])
            print("-----\n")
            found += 1
            break
        if found >= 2:
            break
    if found >= 2:
        break
print(f"found: {found}")
