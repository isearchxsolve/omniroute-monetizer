"""Time-boxed hunt: what triggers the ~100s auto-combo/catalog rebuild?
Search compiled chunks for models.dev sync scheduler, catalog cache TTLs,
and settings keys that could act as a kill-switch. T11-safe (read-only)."""
import os, re, glob

CHUNK_DIR = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"
files = glob.glob(os.path.join(CHUNK_DIR, "*.js"))
print(f"scanning {len(files)} chunks")

# 1) models.dev sync related identifiers + nearby numeric constants
pat_sync = re.compile(r"modelsDevSync|MODELS_DEV_SYNC|models_dev_sync|modelsDev", re.I)
pat_num = re.compile(r"(?:interval|ttl|expires|cache|every|period)[\"']?\s*[:=]\s*([0-9_eE.+]{2,12})")

hits = {}
for f in files:
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if "modelsDev" not in s and "MODELS_DEV" not in s:
        continue
    name = os.path.basename(f)
    # find all positions of modelsDev mentions and capture surrounding 200 chars
    ctx = []
    for m in re.finditer(r"modelsDev\w*|MODELS_DEV\w*", s):
        seg = s[max(0, m.start()-120):m.end()+160].replace("\n", " ")
        ctx.append((m.group(0), seg))
    # dedupe by identifier
    seen = set()
    uniq = []
    for ident, seg in ctx:
        key = seg[:80]
        if key in seen: continue
        seen.add(key); uniq.append((ident, seg))
    hits[name] = uniq[:25]

for name, uniq in sorted(hits.items(), key=lambda kv: -len(kv[1])):
    print(f"\n===== {name} ({len(uniq)} contexts) =====")
    for ident, seg in uniq:
        print(f"  [{ident}] ...{seg}...")

# 2) any numeric TTL-ish constants between 60s and 200s anywhere near 'cache'/'ttl'/'expire'
print("\n\n########## TTL-ish constants 60_000..200_000 near cache/ttl/expire words ##########")
pat2 = re.compile(r".{60}(?:TTL|ttl|expiresAt|expires_at|cacheExpir|staleAfter|refreshInterval|syncInterval).{0,80}?\b(6[0-9]{4}|7[0-9]{4}|8[0-9]{4}|9[0-9]{4}|1[0-2][0-9]{4}|120000|180000|100000|1e5|9e4|6e4)\b")
for f in files:
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for m in pat2.finditer(s):
        seg = m.group(0).replace("\n", " ")
        print(f"{os.path.basename(f)}: ...{seg[-180:]}...")
