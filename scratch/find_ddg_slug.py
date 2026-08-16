#!/usr/bin/env python3
"""Find exact DuckDuckGo provider id(s) in OmniRoute dist config."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

fp = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\open-sse_00r5dfh._.js"
t = open(fp, encoding="utf-8", errors="ignore").read()

for pat in [r'id:"[^"]*duck[^"]*"', r'id:"[^"]*ddg[^"]*"', r'"duckduckgo[^"]*"']:
    hits = sorted(set(re.findall(pat, t)))
    print(pat, "->", hits)

# also show context around duckduckgo mentions
for m in re.finditer(r'duckduckgo', t):
    s = max(0, m.start() - 200)
    print("\n--- context ---")
    print(t[s:m.start() + 250].replace("\n", " "))
