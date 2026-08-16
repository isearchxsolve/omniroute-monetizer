#!/usr/bin/env python3
"""Count authType values across OmniRoute config chunks + list optional/none owners."""
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"
files = glob.glob(os.path.join(DIST, "**", "*config*.js"), recursive=True)
print(f"{len(files)} config chunk(s)")

text = ""
for x in files:
    try:
        text += open(x, encoding="utf-8", errors="ignore").read()
    except Exception:
        pass

for v in ("optional", "none", "apikey", "oauth", "optional_apikey"):
    print(f'authType:"{v}" count = {text.count(chr(34) + v + chr(34)) if False else text.count("authType:" + chr(34) + v + chr(34))}')

# find owners of optional/none
pat = re.compile(r'authType:"(optional|none)"')
id_pat = re.compile(r'id:"([a-z0-9\-]+)"')
found = {}
for m in pat.finditer(text):
    start = max(0, m.start() - 2500)
    chunk = text[start:m.start()]
    ids = id_pat.findall(chunk)
    if ids:
        found[ids[-1]] = m.group(1)
print(f"\nowners of optional/none authType: {len(found)}")
for pid in sorted(found):
    print(f"  {pid} -> {found[pid]}")
