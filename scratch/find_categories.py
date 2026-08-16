#!/usr/bin/env python3
"""Find category registries (NO_AUTH_PROVIDERS etc.) and supportsApiKeyOnFreeProvider."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"

targets = ["supportsApiKeyOnFreeProvider", "NO_AUTH_PROVIDERS", "WEB_COOKIE_PROVIDERS", "SEARCH_PROVIDERS"]
seen = set()

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
        for tgt in targets:
            if tgt in t and (tgt, fp) not in seen:
                seen.add((tgt, fp))
                # find definition
                for m in re.finditer(re.escape(tgt) + r'\s*[=:]\s*', t):
                    s = max(0, m.start() - 200)
                    e = min(len(t), m.end() + 1200)
                    seg = t[s:e].replace("\n", " ")
                    print(f"=== {tgt} in {os.path.basename(fp)}")
                    print(seg[:1500])
                    print("-----\n")
                    break
        if len(seen) >= 8:
            break
    if len(seen) >= 8:
        break
