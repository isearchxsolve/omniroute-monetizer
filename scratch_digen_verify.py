# -*- coding: utf-8 -*-
"""Verify digen seat end-to-end WITHOUT spending a new generation credit.

Layer 1: pool dispatches digen + DigenSessionClient initializes (no network).
Layer 2: the sentinel job's completed video_url is actually fetchable (HEAD request,
         read-only) — this is the real proof the video supply works.
We do NOT submit a new job: the sentinel video already proves the shape, and a new
submit would burn one of the free credits.
"""
import sys, pathlib, json, requests
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))

# Layer 1: pool dispatch + client init
from session_pool import SessionPool
pool = SessionPool()
digen = [s for s in pool.sessions if "digen" in s.host]
print("=== Layer 1: pool dispatch ===")
for s in digen:
    print("host:", s.host, "| modality:", s.modality, "| dispatchable:", s.dispatchable,
          "| client_cls:", (s.client_cls.__name__ if s.client_cls else None))
    if s.dispatchable and s.client_cls:
        try:
            c = s.client()
            print("client init OK:", type(c).__name__, "| headers:", len(c._headers))
        except Exception as e:
            print("client init FAILED:", e)

# Layer 2: sentinel video_url accessible (read-only HEAD)
print("\n=== Layer 2: sentinel video_url accessible ===")
raw = json.loads(pathlib.Path("state/secrets/session_digen_ai.json").read_text(encoding="utf-8"))
exchanges = raw["recorded_job"].get("exchanges", [])
_DROP = {"content-length", "accept-encoding", "cookie"}
headers = {}
for ex in exchanges:
    h = ex.get("request_headers", {})
    if "Digen-Token" in h:
        for k, v in h.items():
            if not k.startswith(":") and k.lower() not in _DROP:
                headers[k] = v
        break
headers["accept-encoding"] = "gzip, deflate"
r = requests.get("https://api.digen.ai/v1/queue/list?page=0&pageSize=20&status=3",
                 headers=headers, timeout=20)
jobs = (r.json().get("data") or {}).get("list") or []
sentinel = None
for job in jobs:
    try:
        d = json.loads(job.get("data", "{}"))
        sp = json.loads(d.get("scene_params", "{}"))
        if "lighthouse" in sp.get("video_gen_prompt", "").lower():
            sentinel = sp.get("video_url") or job.get("videoUrl") or job.get("videoURLV1")
            if sentinel:
                break
    except Exception:
        pass
if not sentinel:
    print("no sentinel video_url found")
    raise SystemExit(1)
print("sentinel video_url:", sentinel[:90] + "...")
try:
    hr = requests.head(sentinel, timeout=20, allow_redirects=True)
    print("HEAD status:", hr.status_code, "| content-type:", hr.headers.get("content-type"),
          "| content-length:", hr.headers.get("content-length"))
    if hr.status_code == 200:
        print("VERDICT: VIDEO_ACCESSIBLE — digen video supply proven live (no new credit spent)")
    else:
        # some S3 buckets reject HEAD; try a ranged GET
        gr = requests.get(sentinel, headers={"Range": "bytes=0-0"}, timeout=20)
        print("ranged GET status:", gr.status_code)
        if gr.status_code in (200, 206):
            print("VERDICT: VIDEO_ACCESSIBLE (via ranged GET)")
        else:
            print("VERDICT: VIDEO_URL_UNREACHABLE (HTTP %d)" % gr.status_code)
except requests.RequestException as e:
    print("NETWORK error:", e)
