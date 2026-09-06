"""Read-only: probe upstream model lists for orcarouter and ainative video support.

Uses the OmniRoute connection API keys (never printed) against each provider's
public models endpoint. Zero spend: model listing is free.
"""
import json
import pathlib
import sys

import requests

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI  # noqa: E402

OUT = pathlib.Path(r"D:\omniroute-monetizer\tmp\upstream_video_probe.json")

c = OmniRouteAPI()
c.login()
conns = {x.get("provider"): x for x in c.get_connections()}

VID = re_pat = None
import re  # noqa: E402
VID = re.compile(r"video|kling|veo|wan|sora|pika|runway|ltx|hailuo|minimax-video|seedance", re.I)

results = {}

# --- orcarouter -----------------------------------------------------------
key = conns["orcarouter"].get("apiKey")
try:
    r = requests.get(
        "https://api.orcarouter.ai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    body = r.json()
    ids = [m.get("id") for m in body.get("data", [])]
    vids = [i for i in ids if i and VID.search(i)]
    results["orcarouter"] = {"http": r.status_code, "total": len(ids), "video_ids": vids}
except Exception as e:
    results["orcarouter"] = {"http": None, "error": repr(e)[:200]}

# --- ainative -------------------------------------------------------------
key = conns["ainative"].get("apiKey")
try:
    r = requests.get(
        "https://api.ainative.studio/api/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    body = r.json()
    # body shape may be {data:[...]} or a bare list
    items = body.get("data") if isinstance(body, dict) else body
    if isinstance(items, dict):
        ids = list(items.keys())
    else:
        ids = [m.get("id") if isinstance(m, dict) else str(m) for m in (items or [])]
    vids = [i for i in ids if i and VID.search(str(i))]
    results["ainative"] = {"http": r.status_code, "total": len(ids), "video_ids": vids[:20]}
except Exception as e:
    results["ainative"] = {"http": None, "error": repr(e)[:200]}

OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
print(json.dumps(results, indent=1))
