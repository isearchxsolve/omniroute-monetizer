#!/usr/bin/env python3
"""Extract all OmniRoute providers with authType optional/none from dist config.
Looks backwards from each authType match to find the owning provider id.
"""
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

DIST = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"
# Target only the provider-config chunks (full dist scan is too slow)
files = [f for f in glob.glob(os.path.join(DIST, "**", "*config*.js"), recursive=True)]
if not files:
    files = glob.glob(os.path.join(DIST, "**", "*.js"), recursive=True)
print(f"scanning {len(files)} config chunk(s)")

found = {}
pat = re.compile(r'authType:"(optional|none)"')
id_pat = re.compile(r'id:"([a-z0-9\-]+)"')

for fp in files:
    try:
        text = open(fp, encoding="utf-8", errors="ignore").read()
    except Exception:
        continue
    for m in pat.finditer(text):
        # look back up to 2000 chars for the nearest id:"..."
        start = max(0, m.start() - 2000)
        chunk = text[start:m.start()]
        ids = id_pat.findall(chunk)
        if ids:
            pid = ids[-1]
            found[pid] = m.group(1)

print(f"providers with authType optional/none: {len(found)}")
for pid in sorted(found):
    print(f"  {pid} -> {found[pid]}")
