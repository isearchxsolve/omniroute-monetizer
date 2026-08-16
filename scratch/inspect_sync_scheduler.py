"""Find: (1) env var that force-stops models.dev sync, (2) default sync interval,
(3) what the sync does (does it rebuild catalog/pricing?). Read-only, T11-safe."""
import os, re, glob

CHUNK_DIR = r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist\.build\next\server\chunks"

# The scheduler logic lives in the _0-*.js chunks we saw. Grab one and extract
# the env var name near the force-stop check, plus default interval constants.
target = None
for f in glob.glob(os.path.join(CHUNK_DIR, "_0-51sfk._.js")):
    target = f
if not target:
    cands = glob.glob(os.path.join(CHUNK_DIR, "_0-*.js"))
    for f in cands:
        s = open(f, encoding="utf-8", errors="replace").read()
        if "modelsDevSyncEnabled" in s and "has(t.trim().toLowerCase())" in s:
            target = f
            break
print("target chunk:", target)
s = open(target, encoding="utf-8", errors="replace").read()

# 1) env var name: look for process.env.X near the stop-check
for m in re.finditer(r"process\.env\.([A-Z0-9_]+)", s):
    name = m.group(1)
    seg = s[max(0, m.start()-150):m.end()+250].replace("\n", " ")
    if "MODELS_DEV" in name or "SYNC" in name or "has(" in seg[:200]:
        print(f"\nENV: {name}\n  ctx: ...{seg}...\n")

# 2) default interval: find where modelsDevSyncInterval default is applied (i(...) call with fallback)
for m in re.finditer(r"i\((?:s|n)\.modelsDevSyncInterval\|\|([0-9e_]+)\)", s):
    print("default interval literal:", m.group(1))
for m in re.finditer(r"modelsDevSyncInterval\|\|([0-9e_]+)", s):
    print("interval fallback literal:", m.group(1))

# 3) setInterval usage in this chunk
for m in re.finditer(r"setInterval\(([^,]{1,40}),\s*([0-9e_]+)\)", s):
    print("setInterval:", m.group(1), "period:", m.group(2))

# 4) the sync function k(): what does it call? print 600 chars after 'async function k('
idx = s.find("async function k(")
if idx >= 0:
    print("\nsync fn body start:\n", s[idx:idx+900].replace("\n", " "))
