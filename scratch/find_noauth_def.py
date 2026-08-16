#!/usr/bin/env python3
"""Find NOAUTH_PROVIDERS definition + supportsApiKeyOnFreeProvider + where duckduckgo-web lives."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

want = {
    "NOAUTH_PROVIDERS": 0,
    "supportsApiKeyOnFreeProvider": 0,
}

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

        # NOAUTH_PROVIDERS definition (assignment)
        if want["NOAUTH_PROVIDERS"] < 1 and re.search(r'NOAUTH_PROVIDERS\s*=', t):
            for m in re.finditer(r'NOAUTH_PROVIDERS\s*=\s*', t):
                s = max(0, m.start() - 50)
                e = min(len(t), m.end() + 2500)
                seg = t[s:e].replace("\n", " ")
                print("=== NOAUTH_PROVIDERS in", os.path.basename(fp))
                print(seg[:2600])
                print("-----\n")
                want["NOAUTH_PROVIDERS"] += 1
                break

        # supportsApiKeyOnFreeProvider definition
        if want["supportsApiKeyOnFreeProvider"] < 1 and re.search(r'supportsApiKeyOnFreeProvider', t):
            for m in re.finditer(r'supportsApiKeyOnFreeProvider["\']?\s*[,:]\s*0\s*,\s*function|function supportsApiKeyOnFreeProvider|supportsApiKeyOnFreeProvider\s*=\s*function', t):
                s = max(0, m.start() - 100)
                e = min(len(t), m.end() + 1200)
                seg = t[s:e].replace("\n", " ")
                print("=== supportsApiKeyOnFreeProvider in", os.path.basename(fp))
                print(seg[:1400])
                print("-----\n")
                want["supportsApiKeyOnFreeProvider"] += 1
                break

        if all(v >= 1 for v in want.values()):
            break
    if all(v >= 1 for v in want.values()):
        break

print("done", want)
