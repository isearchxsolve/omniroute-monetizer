#!/usr/bin/env python3
"""Dump getDatabaseSettings body from the localDb chunk."""
import re

P = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks\src_lib_localDb_ts_11n2jj9._.js"
with open(P, "r", encoding="utf-8", errors="replace") as f:
    data = f.read()

print(f"file length: {len(data)}")
# find all occurrences of the identifier
idxs = [m.start() for m in re.finditer(r"getDatabaseSettings", data)]
print(f"occurrences: {len(idxs)}")
for i in idxs:
    print(f"\n=== @ {i} ===")
    print(data[max(0, i-300):i+900])
    print("---")
