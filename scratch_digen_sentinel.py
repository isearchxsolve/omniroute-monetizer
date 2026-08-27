# -*- coding: utf-8 -*-
"""Check the digen sentinel job's completion state + videoUrl from the live queue.
Read-only. If the original sentinel job has a videoUrl, the full submit->poll->video
shape is proven with this token WITHOUT spending new generation credits.
"""
import json, pathlib, requests

raw = json.loads(pathlib.Path("state/secrets/session_digen_ai.json").read_text(encoding="utf-8"))
exchanges = raw["recorded_job"].get("exchanges", [])
_DROP_HDR = {"content-length", "accept-encoding", "cookie"}
headers = {}
for ex in exchanges:
    h = ex.get("request_headers", {})
    if "Digen-Token" in h:
        for k, v in h.items():
            if not k.startswith(":") and k.lower() not in _DROP_HDR:
                headers[k] = v
        break
headers["accept-encoding"] = "gzip, deflate"

# status=3 = completed jobs
r = requests.get("https://api.digen.ai/v1/queue/list?page=0&pageSize=20&status=3",
                 headers=headers, timeout=20)
j = r.json()
jobs = (j.get("data") or {}).get("list") or []
print("completed jobs:", len(jobs))
for job in jobs:
    cid = job.get("cid")
    created = job.get("createdAt")
    data = job.get("data")
    prompt = ""
    vurl = ""
    try:
        d = json.loads(data) if isinstance(data, str) else data
        sp = json.loads(d.get("scene_params", "{}")) if isinstance(d.get("scene_params"), str) else d.get("scene_params", {})
        prompt = sp.get("video_gen_prompt", "")
        vurl = sp.get("video_url", "") or job.get("videoUrl") or job.get("videoURLV1") or ""
    except Exception:
        pass
    print("---")
    print("cid:", cid, "| createdAt:", created)
    print("prompt:", prompt[:80])
    print("video_url:", (vurl[:100] + "...") if vurl else "(none)")
    if "lighthouse" in prompt.lower() or "omni" in prompt.lower():
        print(">>> THIS IS THE SENTINEL JOB <<<")
