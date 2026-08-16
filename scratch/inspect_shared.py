#!/usr/bin/env python3
"""Inspect src_shared_1c0r6t9._.js: find set x (free providers with apikey support)
and NOAUTH_PROVIDERS / duckduckgo-web membership."""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

fp = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks\src_shared_1c0r6t9._.js"
t = open(fp, encoding="utf-8", errors="ignore").read()
print("file size:", len(t))

# find supportsApiKeyOnFreeProvider and walk back to find the set it uses
m = re.search(r'supportsApiKeyOnFreeProvider["\']?\s*[,:]\s*0\s*,\s*function\(e\)\{return"string"==typeof e&&(\w+)\.has\(e\)\}', t)
if m:
    setname = m.group(1)
    print("set name:", setname)
    # find its definition: <name>=new Set([...])
    for mm in re.finditer(re.escape(setname) + r'\s*=\s*new Set\(\[', t):
        s = mm.start()
        e = min(len(t), mm.end() + 1500)
        seg = t[s:e]
        close = seg.find("])")
        print("SET CONTENT:", seg[:close + 2])
        break
else:
    print("pattern not found; searching loosely")
    for mm in re.finditer(r'new Set\(\[[^\]]{5,400}\]\)', t):
        print("set:", mm.group(0)[:420])
        print("---")

# duckduckgo-web occurrences
print("\nduckduckgo-web hits:", t.count("duckduckgo-web"))
for m in re.finditer(r'duckduckgo-web', t):
    s = max(0, m.start() - 300)
    e = min(len(t), m.end() + 150)
    print(t[s:e].replace("\n", " "))
    print("-----")

# NOAUTH
print("\nNOAUTH hits:", t.count("NOAUTH"))
for m in re.finditer(r'NOAUTH\w*', t):
    s = max(0, m.start() - 150)
    e = min(len(t), m.end() + 300)
    print(t[s:e].replace("\n", " "))
    print("-----")
    break
