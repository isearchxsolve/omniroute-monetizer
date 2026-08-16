#!/usr/bin/env python3
"""Find the catalog route + diagnostic headers + settings parse to build a
decisive runtime test for whether the read path Zod-validates the TTL."""
import os
import re

CHUNK_DIR = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

# 1) find getCatalogDiagnosticsHeaders implementation
DIAG_PATS = [
    re.compile(r"function\s+getCatalogDiagnosticsHeaders"),
    re.compile(r"getCatalogDiagnosticsHeaders\s*=\s*"),
    re.compile(r"getCatalogDiagnosticsHeaders\s*:\s*"),
]
# 2) find files that have BOTH the schema field and a .parse( call
hits_parse = []
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
        for pat in DIAG_PATS:
            for m in pat.finditer(data):
                diag_hits.append((fn, m.start(), data, pat.pattern))
        # settings schema + parse in same file
        if "modelCatalogCacheTtlMs" in data and ".parse(" in data:
            hits_parse.append((fn, len(data), data))

print(f"getCatalogDiagnosticsHeaders def hits: {len(diag_hits)}")
seen = set()
for fn, off, data, pat in diag_hits:
    start = max(0, off - 40)
    end = min(len(data), off + 600)
    ctx = data[start:end]
    if ctx[:80] in seen:
        continue
    seen.add(ctx[:80])
    print(f"\n### DIAG {fn} @ {off} [{pat}]")
    print(ctx)
    print("-" * 50)
    if len(seen) >= 6:
        break

print(f"\n\nfiles with BOTH modelCatalogCacheTtlMs AND .parse(: {len(hits_parse)}")
for fn, ln, data in hits_parse[:12]:
    # count parse calls
    np = len(re.findall(r"\.parse\(", data))
    nsp = len(re.findall(r"\.safeParse\(", data))
    print(f"  {fn} (len={ln}, .parse={np}, .safeParse={nsp})")
