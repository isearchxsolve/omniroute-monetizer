"""Find how modelCatalogCacheTtlMs is consumed: the function that reads it from
settings and the cache mechanism it feeds. Also find the catalog builder + any
non-TTL invalidation (timers, events, provider updates)."""
import re, os, glob

CHUNKS = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"
files = glob.glob(os.path.join(CHUNKS, "*.js"))

# Find chunks where modelCatalogCacheTtlMs appears near a settings read or a cache call
candidates = []
for f in files:
    try:
        src = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    idxs = [m.start() for m in re.finditer(r"modelCatalogCacheTtlMs", src)]
    if not idxs:
        continue
    # score: does it also mention catalog + (cache|memo|ttl) in a code (non-mapping) way?
    code_hits = []
    for i in idxs:
        ctx = src[max(0,i-400):i+400]
        # skip the settings-mapping table style ["modelCatalogCacheTtlMs"]
        if re.search(r'\["modelCatalogCacheTtlMs"\]|modelCatalogCacheTtlMs:\["modelCatalogCacheTtlMs"\]', ctx):
            continue
        code_hits.append((i, ctx))
    if code_hits:
        candidates.append((os.path.basename(f), len(idxs), code_hits))

print("chunks with CODE-level TTL usage:", len(candidates))
for fname, n, hits in candidates:
    print(f"\n########## {fname} (total {n} refs, {len(hits)} code-level)")
    for pos, ctx in hits[:4]:
        print(f"\n--- @{pos}")
        print(ctx.replace("\n", " ")[:700])
