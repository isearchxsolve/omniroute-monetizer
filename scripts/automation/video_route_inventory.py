"""Enumerate EVERY video-capable model across the live OmniRoute inventory.

Answers one question only: which video models exist, and on which connections, so the operator
can see the true candidate list before any of them is tested. Read-only -- generates nothing,
spends nothing, touches no provider endpoint.
"""
import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from omniroute_api import OmniRouteAPI, save_json  # noqa: E402

# Words that mean "this route makes moving pictures". Deliberately broad -- a false positive here
# costs one wasted probe, a false negative silently hides a working video model from the operator.
#
# MEASURED 2026-08-23: the first version of this pattern used a bare `kling`, which matched
# thinkingmachines/inkLING on 8 different providers and inflated the count by ~25 phantom routes.
# It also used a bare `hunyuan`, matching tencent/hunyuan-a13b-instruct -- a TEXT LLM. Both families
# share a name with a video model, so the word alone proves nothing; the boundary and the -video
# suffix do.
VIDEO_RE = re.compile(
    r"video|t2v|i2v|v2v|txt2vid|img2vid|text-to-video|image-to-video|"
    r"\bveo\b|\bsora\b|\bwan\b|\bkling|hunyuan-?video|\bltx\b|runway|\bgen-?[34]\b|pika|"
    r"luma-?(?:photon|ray|dream)|\bray-?[123]\b|minimax-?video|hailuo|seedance|mochi|cogvideo|"
    r"animate|zeroscope|framepack|lightricks|dreamina|vidu|allegro|stable-?video|\bsvd\b",
    re.I)

# Routes whose name trips VIDEO_RE but which are demonstrably NOT video generators.
NOT_VIDEO_RE = re.compile(
    r"inkling|"                        # thinkingmachines/inkling -- a text LLM, matched by "kling"
    r"video-detector|"                 # nvidia/ai-synthetic-video-detector -- classifies, not creates
    r"wan-?image|wan-?2\.\d-?image",    # segmind/pollinations wan IMAGE variants
    re.I)

api = OmniRouteAPI()
conns = api.get_connections()
print(f"connections: {len(conns)}")

rows = []
for c in conns:
    cid = c.get("id") or c.get("_id") or ""
    slug = c.get("provider") or c.get("providerKey") or c.get("name") or "?"
    # The live records use isActive/testStatus, NOT active/enabled -- reading the wrong field made
    # every one of 115 connections report INACTIVE on the first run of this script.
    active = str(c.get("isActive", "")).lower() == "true"
    status = str(c.get("testStatus", "") or "")
    try:
        models = api.connection_models(cid) or []
    except Exception as exc:
        print(f"  {slug:<22} MODELS_ERROR {type(exc).__name__}")
        continue
    hits = [m for m in models
            if VIDEO_RE.search(str(m)) and not NOT_VIDEO_RE.search(str(m))]
    if hits:
        rows.append({"provider": slug, "cid": cid, "active": active, "test_status": status,
                     "total_models": len(models), "video_models": sorted(hits)})
    print(f"  {slug:<22} active={str(active):<5} status={status:<10} "
          f"models={len(models):<4} video={len(hits)}")

print()
print("=" * 72)
print("VIDEO-CAPABLE ROUTES FOUND")
print("=" * 72)
total = 0
for r in sorted(rows, key=lambda x: (not x["active"], x["provider"])):
    flag = "ACTIVE  " if r["active"] else "INACTIVE"
    print(f"\n[{flag}] {r['provider']}  ({len(r['video_models'])} of {r['total_models']}) "
          f"status={r['test_status']}")
    for m in r["video_models"]:
        print(f"    {r['provider']}/{m}")
        total += 1
print(f"\nTOTAL video routes: {total} across {len(rows)} providers "
      f"({sum(1 for r in rows if r['active'])} active)")

save_json("video_route_inventory.json", {"providers": rows, "total_video_routes": total})
