#!/usr/bin/env python3
"""Find the getDatabaseSettings implementation and determine whether it applies
the Zod schema parse (which would enforce the TTL clamp on read)."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

# Look for getDatabaseSettings definition and any .parse( near settings hydration
PATTERNS = {
    "getDatabaseSettings_def": re.compile(r"(function\s+\w*getDatabaseSettings|getDatabaseSettings\s*[:=]\s*(?:async\s*)?(?:function|\())"),
    "parse_call": re.compile(r"\.parse\("),
    "safeParse_call": re.compile(r"\.safeParse\("),
}

# First, find files that define getDatabaseSettings
defs = []
n = 0
for root, _dirs, files in os.walk(CHUNK_DIR):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        n += 1
        p = os.path.join(root, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except Exception:
            continue
        if "getDatabaseSettings" in data:
            ndef = len(PATTERNS["getDatabaseSettings_def"].findall(data))
            nparse = len(PATTERNS["parse_call"].findall(data))
            nsafe = len(PATTERNS["safeParse_call"].findall(data))
            defs.append((fn, len(data), ndef, nparse, nsafe, data))

print(f"scanned {n} files; files mentioning getDatabaseSettings: {len(defs)}")
print("=" * 70)
# Show files that have an actual definition (ndef>0)
for fn, ln, ndef, nparse, nsafe, data in defs:
    if ndef > 0:
        print(f"\n### DEF in {fn} (len={ln}, defs={ndef}, .parse={nparse}, .safeParse={nsafe})")
        for m in PATTERNS["getDatabaseSettings_def"].finditer(data):
            start = max(0, m.start() - 60)
            end = min(len(data), m.end() + 500)
            print(f"  @ {m.start()}:")
            print("  " + data[start:end].replace("\n", "\n  "))
            print("  ---")
