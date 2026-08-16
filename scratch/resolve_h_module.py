#!/usr/bin/env python3
"""Resolve the getDatabaseSettings implementation.
The localDb barrel re-exports h.getDatabaseSettings. Find module h's source,
then dump the function body to see if it calls .parse()/.safeParse()."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"
LOCALDB = os.path.join(CHUNK_DIR, "src_lib_localDb_ts_11n2jj9._.js")

with open(LOCALDB, "r", encoding="utf-8", errors="replace") as f:
    data = f.read()

print(f"localDb length: {len(data)}")
# Show the import section (first 1500 chars) to find what h is
print("=== HEAD (imports) ===")
print(data[:1500])
print("\n=== find 'h=' or var declarations ===")
# find where h is assigned, e.g. h=e.i(12345)
for m in re.finditer(r"\bh\s*=\s*e\.i\((\d+)\)", data):
    print(f"  h = e.i({m.group(1)}) at {m.start()}")
# also generic: list all e.i imports
print("\n=== all e.i() imports in head ===")
for m in re.finditer(r"e\.i\((\d+)\)", data[:2000]):
    print(f"  e.i({m.group(1)})")
