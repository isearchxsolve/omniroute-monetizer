#!/usr/bin/env python3
"""Find which category registry contains duckduckgo-web, and the no-auth registry."""
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
        if "mcp-server" in fp:
            continue
        try:
            t = open(fp, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        if '"no-auth"' not in t and "'no-auth'" not in t:
            continue
        # find the no-auth category object definition
        for m in re.finditer(r'"no-auth"\s*:\s*\{', t):
            s = max(0, m.start() - 100)
            e = min(len(t), m.end() + 3000)
            seg = t[s:e].replace("\n", " ")
            print("=== no-auth registry in", os.path.basename(fp))
            print(seg[:3200])
            print("-----\n")
            break
        # where is duckduckgo-web referenced in this file?
        for m in re.finditer(r'duckduckgo-web', t):
            s = max(0, m.start() - 400)
            e = min(len(t), m.end() + 200)
            seg = t[s:e].replace("\n", " ")
            print("=== ddg context in", os.path.basename(fp))
            print(seg[:700])
            print("-----\n")
            break
        break
