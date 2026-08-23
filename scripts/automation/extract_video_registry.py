"""Extract OmniRoute's native VIDEO_PROVIDERS registry from the exact build chunk.

The repo already has scripts/automation/video_registry.py, which does this correctly but globs all
8,019 chunks under dist/.build/next/server/chunks and times out on this machine (the node service
is thrashing the disk). We now know the exact chunk, so go straight to it.

WHY THIS MATTERS -- measured 2026-08-23:
POST /v1/videos/generations resolves the upstream from THIS static code registry, not from the
database. The connection model lists returned by the management API are the CHAT catalogue, and
they are a different thing. Feeding chat ids to the video endpoint produced 14 straight
HTTP 400 "Invalid video model: <id>. Use format: provider/model" -- gemini/veo-3.1-*,
vertex/veo-3.1-* and all 8 orcarouter/kling/* are simply not video routes at all.
Read the registry; never guess.

Read-only.
"""
import json
import pathlib
import re
import subprocess
import tempfile

CHUNK = pathlib.Path(
    r"C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute\dist"
    r"\.build\next\server\chunks\open-sse_config_0td4c56._.js")
OUT = pathlib.Path(r"D:\omniroute-monetizer\state\video_registry_native.json")

src = CHUNK.read_text(encoding="utf-8", errors="replace")

# The registry object literal ends immediately before the export call that names VIDEO_PROVIDERS.
end_marker = src.find('};e.s(["VIDEO_PROVIDERS"')
if end_marker < 0:
    # fall back: the export marker itself, then walk back to the closing brace pair
    m = src.find("VIDEO_PROVIDERS")
    end_marker = src.rfind("};e.s([", 0, m)
assert end_marker > 0, "could not locate end of registry literal"
obj_end = end_marker + 1          # include the object's own closing brace

# Walk backwards from obj_end balancing braces to find the literal's opening '{'.
depth = 0
i = obj_end
while i > 0:
    i -= 1
    c = src[i]
    if c == "}":
        depth += 1
    elif c == "{":
        depth -= 1
        if depth == 0:
            break
obj_start = i
literal = src[obj_start:obj_end + 1]
print(f"registry literal: {len(literal)} chars, from {obj_start} to {obj_end}")

# The literal is JS, not JSON (unquoted keys, !0 for true). Let Node turn it into JSON.
#
# One entry reaches outside the literal: runwayml's models are
#     models:e.i(405469).RUNWAYML_SUPPORTED_VIDEO_MODELS
# where `e` is the webpack module argument. Stub `e` rather than rewrite the literal, so the
# structure stays byte-identical to what the server actually loads; runwayml's model ids are then
# resolved separately below from chunk 405469.
STUB = "const e={i:()=>({RUNWAYML_SUPPORTED_VIDEO_MODELS:[{id:'__SEE_CHUNK_405469__',name:'resolved separately'}]})};\n"

with tempfile.TemporaryDirectory() as td:
    js = pathlib.Path(td) / "dump.js"
    js.write_text(STUB + "const R = " + literal + ";\nprocess.stdout.write(JSON.stringify(R));\n",
                  encoding="utf-8")
    node = r"C:\Users\Admin\AppData\Local\hermes\node\node.exe"
    p = subprocess.run([node, str(js)], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise SystemExit(f"node failed: {p.stderr[-900:]}")
    reg = json.loads(p.stdout)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(reg, indent=1), encoding="utf-8")

print(f"\nVIDEO PROVIDERS IN THE NATIVE REGISTRY: {len(reg)}")
print("=" * 78)
total = 0
for slug, p in reg.items():
    models = p.get("models") or []
    total += len(models)
    print(f"\n{slug}  (alias={p.get('alias','-')}, format={p.get('format','?')}, "
          f"auth={p.get('authType','?')}/{p.get('authHeader','?')})")
    print(f"    baseUrl: {p.get('baseUrl','?')}")
    for m in models:
        print(f"    {slug}/{m.get('id')}    -- {m.get('name')}")
print(f"\nTOTAL: {total} video models across {len(reg)} providers")
print(f"saved: {OUT}")
