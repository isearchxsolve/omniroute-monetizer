"""Which video routes does OmniRoute itself hold credentials for?

THE CORRECTION THIS SCRIPT EXISTS FOR -- 2026-08-23:
video_capability_matrix.py buckets routes by whether the key sits in our own
state/generated_keys.json. That is the wrong test. POST /v1/videos/generations takes credentials
from OmniRoute's OWN configured connection for that provider, so a route can be perfectly usable
while our harvest file knows nothing about it. "need a key" in that matrix means "we did not
harvest this key", NOT "the gateway cannot authenticate".

So the real shortlist is:
    registry provider  AND  handler implemented  AND  OmniRoute has an ACTIVE connection
and that is what this prints, in priority order.

Provider slugs differ between the two worlds (the registry calls it `vertex`, `googleflow`,
`alibaba`; connections may use other names), so matching is done on a normalised slug plus a small
table of known aliases rather than on exact equality.

Read-only.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI  # noqa: E402

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
OUT = ROOT / "state" / "video_credential_map.json"

# The format strings the handler chain actually dispatches (see video_capability_matrix.py).
IMPLEMENTED = {
    "vertex-veo", "google-flow", "comfyui", "sdwebui-video", "kie-video", "runwayml",
    "haiper-video", "veoaifree-web", "leonardo-video", "deepinfra-video", "dashscope-video",
    "segmind", "novita-video", "xai-video", "adobe-firefly-video",
}

# Registry slug -> extra connection slugs that mean the same upstream account.
ALIASES = {
    "vertex": {"vertex", "vertexai", "vertex-ai", "gcp-vertex", "google-vertex"},
    "googleflow": {"googleflow", "google-flow", "flow", "googlelabs", "google-labs"},
    "alibaba": {"alibaba", "dashscope", "bailian", "aliyun", "qwen", "qwen-cloud"},
    "bailian-coding-plan": {"bailian-coding-plan", "bailian", "dashscope"},
    "qwen-cloud": {"qwen-cloud", "qwen", "dashscope", "alibaba"},
    "qwen-cloud-token-plan": {"qwen-cloud-token-plan", "qwen-cloud", "qwen"},
    "adobe-firefly": {"adobe-firefly", "adobe", "firefly"},
    "xai": {"xai", "grok", "x-ai"},
    "deepinfra": {"deepinfra"},
    "novita": {"novita"},
    "segmind": {"segmind"},
    "kie": {"kie", "kieai", "kie-ai"},
    "haiper": {"haiper"},
    "leonardo": {"leonardo", "leonardoai"},
    "runwayml": {"runwayml", "runway"},
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


reg = json.loads((ROOT / "state" / "video_registry_native.json").read_text(encoding="utf-8"))
res_path = ROOT / "state" / "video_proofs" / "sweep_all_results.json"
tested = {}
if res_path.exists():
    for r in json.loads(res_path.read_text(encoding="utf-8"))["results"]:
        tested[r["model"]] = r

api = OmniRouteAPI()
conns = api.get_connections()

# Build normalised-slug -> best connection record. "Best" = active beats inactive.
by_slug: dict[str, dict] = {}
for c in conns:
    for field in ("provider", "name", "providerId", "slug"):
        v = c.get(field)
        if not v:
            continue
        k = norm(v)
        if not k:
            continue
        cur = by_slug.get(k)
        act = str(c.get("isActive", "")).lower() == "true"
        if cur is None or (act and str(cur.get("isActive", "")).lower() != "true"):
            by_slug[k] = c

print(f"OmniRoute connections: {len(conns)}  ({len(by_slug)} distinct normalised slugs)")
print()

rows = []
for slug, p in reg.items():
    if p.get("format") not in IMPLEMENTED:
        continue                                   # dead on arrival, covered elsewhere
    cands = {norm(x) for x in ALIASES.get(slug, {slug})} | {norm(slug), norm(p.get("alias") or "")}
    cands.discard("")
    hit, matched_on = None, None
    for k in sorted(cands):
        if k in by_slug:
            hit, matched_on = by_slug[k], k
            break
    models = [m["id"] for m in (p.get("models") or []) if "__SEE_CHUNK" not in str(m.get("id"))]
    untested = [m for m in models if f"{slug}/{m}" not in tested]
    rows.append({
        "provider": slug,
        "format": p.get("format"),
        "auth": p.get("authType"),
        "local": "localhost" in (p.get("baseUrl") or ""),
        "conn_found": hit is not None,
        "conn_matched_on": matched_on,
        "conn_name": (hit or {}).get("name"),
        "conn_active": str((hit or {}).get("isActive", "")).lower() == "true",
        "conn_status": str((hit or {}).get("testStatus", "") or ""),
        "models": models,
        "untested": untested,
    })


def prio(r: dict) -> tuple:
    # 0 = no auth at all; 1 = live active connection; 2 = connection but not healthy; 3 = nothing
    if r["auth"] == "none":
        return (0, r["provider"])
    if r["conn_active"] and r["conn_status"] in ("active", "success", ""):
        return (1, r["provider"])
    if r["conn_found"]:
        return (2, r["provider"])
    return (3, r["provider"])


LABEL = {0: "NO AUTH NEEDED", 1: "LIVE CONNECTION", 2: "connection unhealthy",
         3: "NO CREDENTIALS ANYWHERE"}
rows.sort(key=prio)

cur = None
shortlist = []
for r in rows:
    band = prio(r)[0]
    if band != cur:
        cur = band
        print("=" * 88)
        print(f"  {LABEL[band]}")
        print("=" * 88)
    extra = "  (local server)" if r["local"] else ""
    cd = ""
    if r["conn_found"]:
        cd = (f"  [conn '{r['conn_name']}' matched on '{r['conn_matched_on']}', "
              f"active={r['conn_active']}, status={r['conn_status'] or '-'}]")
    print(f"  {r['provider']:<24} {len(r['models']):>2} models, "
          f"{len(r['untested']):>2} untested{extra}{cd}")
    if band in (0, 1) and r["untested"]:
        shortlist.extend(f"{r['provider']}/{m}" for m in r["untested"])

print()
print("=" * 88)
print(f"  WORTH TESTING NEXT: {len(shortlist)} routes that are untested AND have a credential path")
print("=" * 88)
for s in shortlist:
    print(f"    {s}")

OUT.write_text(json.dumps({"rows": rows, "shortlist": shortlist}, indent=1), encoding="utf-8")
print(f"\nsaved: {OUT}")
