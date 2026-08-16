#!/usr/bin/env python3
"""
Discover all valid provider slugs accepted by POST /api/providers.
"""
import re
from pathlib import Path

dist_chunks = Path(r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks")

valid_slugs = set()
for f in dist_chunks.glob("*.js"):
    text = f.read_text(encoding="utf-8", errors="ignore")
    # Search for enum definitions or provider schemas
    matches = re.findall(r'provider:\w+\.enum\(\[([^\]]+)\]\)', text)
    for m in matches:
        items = [i.strip().strip('"\'') for i in m.split(',')]
        valid_slugs.update(items)

print(f"[+] Found {len(valid_slugs)} accepted provider slugs in schema:")
for s in sorted(valid_slugs):
    print(f"  - {s}")
