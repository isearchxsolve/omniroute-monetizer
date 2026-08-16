#!/usr/bin/env python3
"""Find isManagedProviderConnectionId across dist (any form)."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

count = 0
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
        if "isManagedProviderConnectionId" not in t:
            continue
        count += 1
        print("===", fp, f"({t.count('isManagedProviderConnectionId')} hits)")
        # show first definition-like occurrence
        for m in re.finditer(r'isManagedProviderConnectionId', t):
            s = max(0, m.start() - 600)
            e = min(len(t), m.end() + 600)
            seg = t[s:e].replace("\n", " ")
            if "function" in seg or "=>" in seg or "includes" in seg:
                print(seg[:1400])
                print("-----")
                break
        if count >= 3:
            break
    if count >= 3:
        break
print(f"\nfiles with symbol: {count}")
