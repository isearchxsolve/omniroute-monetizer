"""Find the model catalog cache TTL settings key in the 3.8.49 bundle.
Upstream #8219/#8215 made it configurable (UI bound 100-60000ms).
Read-only, T11-safe."""
import os, re, glob

CHUNK_DIR = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"
pat = re.compile(r"model(?:Catalog|List)?Cache(?:Ttl|TTL|Version)?|catalogCacheTtl|modelListCache", re.I)

found = {}
for f in glob.glob(os.path.join(CHUNK_DIR, "*.js")):
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if "atalogCache" not in s and "odelListCache" not in s:
        continue
    name = os.path.basename(f)
    segs = set()
    for m in re.finditer(r"[A-Za-z_$][\w$]*[Cc]ache(?:Ttl|TTL|Version)[\w$]*", s):
        ident = m.group(0)
        seg = s[max(0, m.start()-100):m.end()+140].replace("\n", " ")
        segs.add((ident, seg[:220]))
    if segs:
        found[name] = list(segs)[:12]

for name, segs in sorted(found.items(), key=lambda kv: -len(kv[1]))[:8]:
    print(f"\n===== {name} =====")
    for ident, seg in segs:
        print(f"  [{ident}] ...{seg}...")

# also: settings schema default value for the TTL key
print("\n########## default TTL value near key ##########")
for f in glob.glob(os.path.join(CHUNK_DIR, "*.js")):
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    for m in re.finditer(r"(modelCatalogCacheTtl|modelListCacheTtl|catalogCacheTtl)[\"']?\s*[:=]\s*([0-9e_]+)", s):
        print(f"{os.path.basename(f)}: {m.group(1)} = {m.group(2)}")
