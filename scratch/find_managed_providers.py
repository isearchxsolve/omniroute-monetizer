#!/usr/bin/env python3
"""Find isManagedProviderConnectionId definition + managed provider list."""
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
        for m in re.finditer(r'function isManagedProviderConnectionId', t):
            s = max(0, m.start() - 300)
            e = min(len(t), m.end() + 2500)
            print("===", fp)
            print(t[s:e].replace("\n", " "))
            print("-----\n")
            found += 1
        if found >= 2:
            break
    if found >= 2:
        break

if not found:
    # try minified pattern
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
            if "isManagedProviderConnectionId" in t and "MANAGED_PROVIDER" in t:
                for m in re.finditer(r'MANAGED_PROVIDER[A-Z_]*\s*=', t):
                    s = max(0, m.start() - 100)
                    e = min(len(t), m.end() + 1500)
                    print("===", fp)
                    print(t[s:e].replace("\n", " "))
                    print("-----\n")
                    found += 1
                    if found >= 2:
                        break
            if found >= 2:
                break
        if found >= 2:
            break
