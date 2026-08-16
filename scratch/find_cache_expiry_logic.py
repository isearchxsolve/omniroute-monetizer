"""Find the actual model-catalog cache implementation: where modelCatalogCacheTtlMs
is READ and compared to Date.now(), and what invalidates the cache besides TTL."""
import re, os, glob

CHUNKS = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"

# Pattern: TTL value used in an expiry comparison
patterns = [
    (r"modelCatalogCacheTtlMs[^;]{0,200}Date\.now", "TTL+Date.now same statement"),
    (r"Date\.now\(\)\s*-\s*\w+\s*[<>]=?\s*\w*[Tt]tl", "now - ts < ttl comparison"),
    (r"[Tt]tl\s*[<>]=?\s*Date\.now\(\)\s*-\s*\w+", "ttl < now - ts comparison"),
]

files = glob.glob(os.path.join(CHUNKS, "*.js"))
print("scanning", len(files), "chunks")

hits = {}
for f in files:
    try:
        src = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for pat, label in patterns:
        for m in re.finditer(pat, src):
            hits.setdefault(os.path.basename(f), []).append((label, m.start(), src[max(0,m.start()-250):m.end()+250]))

for fname, lst in hits.items():
    print(f"\n########## {fname}: {len(lst)} hits")
    for label, pos, ctx in lst[:6]:
        print(f"\n--- [{label}] @{pos}")
        print(ctx.replace("\n", " ")[:600])
