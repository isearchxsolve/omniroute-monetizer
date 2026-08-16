"""Part 1: check bundle for a server-side clamp of modelCatalogCacheTtlMs (UI cap was 60000ms).
Part 2: PUT the TTL at top level (route reads s.modelCatalogCacheTtlMs directly) and verify."""
import os, re, glob, json, requests

CHUNK_DIR = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"

print("########## clamp check ##########")
for f in glob.glob(os.path.join(CHUNK_DIR, "*.js")):
    try:
        s = open(f, encoding="utf-8", errors="replace").read()
    except Exception:
        continue
    if "modelCatalogCacheTtlMs" not in s:
        continue
    for m in re.finditer(r".{80}modelCatalogCacheTtlMs.{160}", s):
        seg = m.group(0).replace("\n", " ")
        if "Math.min" in seg or "6e4" in seg or "60000" in seg or "clamp" in seg.lower():
            print(f"{os.path.basename(f)}: ...{seg}...\n")
    # also find where the TTL is READ for the memo (getModelCatalogCacheTtl-ish fn)
    for m in re.finditer(r"function\s+\w+\([^)]*\)\{[^}]{0,200}modelCatalogCacheTtlMs[^}]{0,200}\}", s):
        print("READER:", os.path.basename(f), "...", m.group(0)[:400].replace("\n", " "), "...\n")

print("########## settings update ##########")
pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip() or "<REDACTED>"
sess = requests.Session()
r = sess.post("http://localhost:20128/api/auth/login", json={"password": pw}, timeout=10)
print("login:", r.status_code)

# top-level key, matching route handler: void 0!==s.modelCatalogCacheTtlMs&&(o.modelCatalogCacheTtlMs=...)
r = sess.put("http://localhost:20128/api/settings", json={"modelCatalogCacheTtlMs": 3600000}, timeout=15)
print("PUT top-level:", r.status_code)

# now fetch settings and search entire JSON for the key
r = sess.get("http://localhost:20128/api/settings", timeout=10)
data = r.json()
flat = json.dumps(data)
print("key present in GET response:", "modelCatalogCacheTtlMs" in flat)
def find_key(obj, key, path=""):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == key:
                out.append((p, v))
            out += find_key(v, key, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += find_key(v, key, f"{path}[{i}]")
    return out
print("found:", find_key(data, "modelCatalogCacheTtlMs"))
print("cache section:", json.dumps(data.get("cache", "ABSENT"))[:400])
