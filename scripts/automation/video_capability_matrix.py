"""Cross-reference the native video registry against the handlers OmniRoute actually implements.

MEASURED 2026-08-23. POST /v1/videos/generations dispatches on providerConfig.format through a
single if/else chain (build chunks open-sse_1y8z7i0._.js and _0a3a476._.js, both identical). Any
registry entry whose format is not in that chain returns
    HTTP 400 "Unsupported video format: <format>"
no matter what credentials you hold. pollinations/default proved this live: it is listed in the
registry as "Pollinations Video (Free)" and it can never work, because pollinations-video has no
handler. Four providers are dead on arrival for this reason.

So a registry entry is NOT evidence a route can work. Both the registry AND the handler chain have
to agree. This script is the only place that check lives.

Read-only.
"""
import json
import pathlib

# The exact format strings dispatched in the handler chain, in source order.
IMPLEMENTED = [
    "vertex-veo", "google-flow", "comfyui", "sdwebui-video", "kie-video", "runwayml",
    "haiper-video", "veoaifree-web", "leonardo-video", "deepinfra-video", "dashscope-video",
    "segmind", "novita-video", "xai-video", "adobe-firefly-video",
]

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
reg = json.loads((ROOT / "state" / "video_registry_native.json").read_text(encoding="utf-8"))
keys = json.loads((ROOT / "state" / "generated_keys.json").read_text(encoding="utf-8"))
have = {k.lower() for k in keys}

# Live results measured this session, keyed by full model id.
res_path = ROOT / "state" / "video_proofs" / "sweep_all_results.json"
tested = {}
if res_path.exists():
    for r in json.loads(res_path.read_text(encoding="utf-8"))["results"]:
        tested[r["model"]] = r

rows = []
for slug, p in reg.items():
    fmt = p.get("format", "?")
    auth = p.get("authType", "?")
    models = [m for m in (p.get("models") or []) if "__SEE_CHUNK" not in str(m.get("id"))]
    rows.append({
        "provider": slug,
        "format": fmt,
        "implemented": fmt in IMPLEMENTED,
        "auth": auth,
        "needs_key": auth not in ("none",),
        "have_key": slug.lower() in have,
        "local": "localhost" in (p.get("baseUrl") or ""),
        "base_url": p.get("baseUrl"),
        "models": [m.get("id") for m in models],
    })

usable = [r for r in rows if r["implemented"]]
dead = [r for r in rows if not r["implemented"]]

print("=" * 90)
print("  DEAD ON ARRIVAL -- in the registry, but NO handler exists. Cannot work, ever.")
print("=" * 90)
for r in dead:
    print(f"  {r['provider']:<22} format={r['format']:<22} {len(r['models'])} models")
    for m in r["models"]:
        print(f"      {r['provider']}/{m}")
print(f"  => {sum(len(r['models']) for r in dead)} models across {len(dead)} providers are unusable")

print()
print("=" * 90)
print("  IMPLEMENTED -- the handler exists, so these are the only real candidates")
print("=" * 90)
order = {"no-auth": 0, "have-key": 1, "need-key": 2}


def bucket(r):
    if not r["needs_key"]:
        return "no-auth"
    return "have-key" if r["have_key"] else "need-key"


for r in sorted(usable, key=lambda x: (order[bucket(x)], x["provider"])):
    b = bucket(r)
    tag = {"no-auth": "NO KEY NEEDED", "have-key": "KEY STORED", "need-key": "need a key"}[b]
    extra = "  (local server)" if r["local"] else ""
    print(f"\n  {r['provider']:<22} {tag:<14} {len(r['models'])} models{extra}")
    for m in r["models"]:
        full = f"{r['provider']}/{m}"
        t = tested.get(full)
        if t:
            v = "PROVEN" if t["verdict"] == "PROVEN" else t["reason"]
            print(f"      {full:<46} tested -> {v} (http {t['http']})")
        else:
            print(f"      {full:<46} not yet tested")

print()
print("=" * 90)
n_impl = sum(len(r["models"]) for r in usable)
n_tested = sum(1 for r in usable for m in r["models"] if f"{r['provider']}/{m}" in tested)
n_proven = sum(1 for t in tested.values() if t["verdict"] == "PROVEN")
print(f"  registry total      : {sum(len(r['models']) for r in rows)} models / {len(rows)} providers")
print(f"  handler implemented : {n_impl} models / {len(usable)} providers")
print(f"  dead on arrival     : {sum(len(r['models']) for r in dead)} models / {len(dead)} providers")
print(f"  tested so far       : {n_tested}")
print(f"  PROVEN working      : {n_proven}")
print("=" * 90)

out = ROOT / "state" / "video_capability_matrix.json"
out.write_text(json.dumps({"implemented_formats": IMPLEMENTED, "providers": rows}, indent=1),
               encoding="utf-8")
print(f"saved: {out}")
