"""Stage 1 hotfix: patch ONLY the modelCatalogCacheTtlMs Zod clamp in sandbox chunks.
.max(6e4) -> .max(6e5) (60s -> 600s ceiling), leaving all other .max(6e4) clamps
(retryDelayMs, fallbackDelayMs, setRetryDelayMs, hedgeDelayMs, minTime) untouched.
Creates .bak backups of each patched file. T11-safe: no secrets.
"""
import os
import re
import shutil
import sys

CHUNKS = r"d:\omniroute-sandbox\node_modules\omniroute\dist\.build\next\server\chunks"

# Unique anchor: the field name immediately precedes the clamp chain.
# Matches e.g. modelCatalogCacheTtlMs:a.z.number().int().min(500).max(6e4)
PATTERN = re.compile(r"(modelCatalogCacheTtlMs:\w+\.z\.number\(\)\.int\(\)\.min\(500\)\.max\()6e4(\))")

TARGETS = [
    "src_shared_0p0h6qs._.js",
    "src_shared_1mmftfa._.js",
    "src_shared_1z-n08e._.js",
]

total = 0
for name in TARGETS:
    path = os.path.join(CHUNKS, name)
    if not os.path.exists(path):
        print(f"[SKIP] {name}: not found")
        continue
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    new, n = PATTERN.subn(r"\g<1>6e5\g<2>", src)
    if n == 0:
        print(f"[WARN] {name}: no modelCatalogCacheTtlMs clamp found (already patched?)")
        continue
    bak = path + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    total += n
    print(f"[OK] {name}: patched {n} occurrence(s), backup -> {os.path.basename(bak)}")

print(f"\nTOTAL patched occurrences: {total}")

# Verify: count remaining .max(6e4) vs new .max(6e5) and confirm other clamps intact
for name in TARGETS:
    path = os.path.join(CHUNKS, name)
    if not os.path.exists(path):
        continue
    with open(path, "r", encoding="utf-8") as f:
        c = f.read()
    m64 = c.count(".max(6e4)")
    m65 = c.count(".max(6e5)")
    ttl65 = len(re.findall(r"modelCatalogCacheTtlMs:\w+\.z\.number\(\)\.int\(\)\.min\(500\)\.max\(6e5\)", c))
    print(f"[VERIFY] {name}: .max(6e4)={m64}  .max(6e5)={m65}  ttl-clamp-now-6e5={ttl65}")

sys.exit(0 if total >= 3 else 1)
