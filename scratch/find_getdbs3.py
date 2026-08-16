#!/usr/bin/env python3
"""Find getDatabaseSettings via e.s([...]) export registration, and find
getCatalogDiagnosticsHeaders to learn observable TTL signals."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

# Turbopack export registration: e.s(["getDatabaseSettings",0,<ref>,...])
REG_RE = re.compile(r'\.s\(\[[^\]]*?"getDatabaseSettings"[^\]]*?\]\)')
DIAG_RE = re.compile(r'getCatalogDiagnosticsHeaders\s*[:=]')
# also look for the function body that reads settings + parses
PARSE_NEAR = re.compile(r'(settingsSchema|SettingsSchema|\.parse\(|\.safeParse\()')

reg_hits = []
diag_hits = []
for root, _dirs, files in os.walk(CHUNK_DIR):
    for fn in files:
        if not fn.endswith(".js"):
            continue
        p = os.path.join(root, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
        except Exception:
            continue
        for m in REG_RE.finditer(data):
            reg_hits.append((fn, m.start(), data))
        for m in DIAG_RE.finditer(data):
            diag_hits.append((fn, m.start(), data))

print(f"e.s registrations of getDatabaseSettings: {len(reg_hits)}")
seen = set()
for fn, off, data in reg_hits:
    start = max(0, off - 40)
    end = min(len(data), off + 260)
    ctx = data[start:end]
    if ctx in seen:
        continue
    seen.add(ctx)
    print(f"\n### REG {fn} @ {off}")
    print(ctx)
    if len(seen) >= 6:
        break

print(f"\n\ngetCatalogDiagnosticsHeaders defs: {len(diag_hits)}")
seen2 = set()
for fn, off, data in diag_hits:
    start = max(0, off - 40)
    end = min(len(data), off + 500)
    ctx = data[start:end]
    if ctx in seen2:
        continue
    seen2.add(ctx)
    print(f"\n### DIAG {fn} @ {off}")
    print(ctx)
    if len(seen2) >= 4:
        break
