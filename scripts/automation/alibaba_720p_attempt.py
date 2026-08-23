"""One properly-specified attempt at alibaba/wan2.7-t2v -- the only route with free quota left.

WHY THIS IS A NEW REQUEST, NOT A RETRY OF A REFUSED ONE:
The first attempt sent only aspect_ratio, so the handler's parameter builder produced no
`resolution` at all and DashScope fell back to its own default (its highest). The job was accepted
and still RUNNING when OmniRoute's ~300s poll window closed:
    HTTP 504 "DashScope task 4e1f0ec0-... timed out (status: RUNNING)"
That is our payload being underspecified, not the provider refusing us -- the same class of fault
as a rejected duration value, which the sweep already allows exactly one correction for.

From the handler (build chunk open-sse_1y8z7i0._.js, function c):
    resolution: accepted as /^(720|1080)p$/i and upper-cased; otherwise derived from `size`
               (max dimension >= 1920 -> 1080P, else 720P)
    ratio:      forwarded for wan2.7-t2v (called as c(params, true))
    duration:   forwarded as Number(duration)
720P is the lowest resolution this handler can express -- there is no 480P path -- so this is the
fastest render we can ask for, and the best chance of finishing inside the poll window.

Also worth knowing: alibaba/happyhorse-1.1-t2v returned "The free quota has been exhausted" while
this route was accepted, so wan2.7-t2v specifically still has free quota. Spend it carefully.

ONE attempt. If it times out again, the conclusion is recorded and the route is left alone.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
from urllib.parse import urlsplit

import requests

BASE = "http://localhost:20128"
GEN_URL = f"{BASE}/v1/videos/generations"
ROOT = pathlib.Path(r"D:\omniroute-monetizer")
OUT = ROOT / "state" / "video_proofs"

MODEL = "alibaba/wan2.7-t2v-2026-06-12"
# THE ACTUAL BLOCKER, FOUND IN THE BUILD (open-sse_1y8z7i0._.js offset 15372):
#     W = Number(a.timeout_ms)>0 ? Number(a.timeout_ms) : 3e5
#     H = Number(a.poll_interval_ms)>0 ? Number(a.poll_interval_ms) : 2500
# `a` is the REQUEST BODY. The 300s poll window that killed both earlier attempts is a default we
# never overrode, not a hard limit -- so `timeout_ms` in the payload raises it. The same pattern
# governs novita, xai, adobe-firefly, runway and haiper, so this one line applies far beyond
# alibaba. 15 minutes is generous for a 5s 720P render.
POLL_MS = 900_000
payload = {
    "model": MODEL,
    "prompt": "a single red balloon drifting upward against a clear blue sky, slow steady shot",
    "duration": 5,
    "resolution": "720p",      # lowest the handler can express -> fastest render
    "aspect_ratio": "16:9",
    "timeout_ms": POLL_MS,
    "poll_interval_ms": 5000,
    "n": 1,
}

print(f"POST {GEN_URL}")
print(f"  model      : {MODEL}")
print(f"  resolution : 720p  (was unset originally -> DashScope defaulted higher and overran)")
print(f"  timeout_ms : {POLL_MS}  (default 300000 was the only thing that failed before)")
print(f"  started    : {time.strftime('%H:%M:%S')} local")
sys.stdout.flush()

res = {"model": MODEL, "payload_resolution": "720p", "payload_timeout_ms": POLL_MS,
       "http": None, "elapsed_s": None,
       "verdict": "NOT_PROVEN", "reason": "", "detail": "", "bytes": None, "is_mp4": False}
t0 = time.time()
try:
    r = requests.post(GEN_URL, json=payload, timeout=POLL_MS / 1000 + 120)
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["http"] = r.status_code
    print(f"\nHTTP {r.status_code} after {res['elapsed_s']}s")
    try:
        body = r.json()
    except Exception:
        body = r.text[:800]
    if r.status_code != 200:
        res["reason"] = f"HTTP_{r.status_code}"
        err = body.get("error") if isinstance(body, dict) else body
        res["detail"] = (err.get("message") if isinstance(err, dict) else str(err))[:600]
        print(f"  {res['detail']}")
    else:
        data = body.get("data") if isinstance(body, dict) else None
        first = data[0] if isinstance(data, list) and data else {}
        url = first.get("url") if isinstance(first, dict) else None
        if not url:
            res["reason"] = "NO_ARTIFACT"
            res["detail"] = f"HTTP 200 but no url; keys={sorted(body.keys())}"
            print(f"  {res['detail']}")
        else:
            p = urlsplit(url)
            print(f"  video url on host {p.netloc} ({len(url)} chars, query hidden) -- downloading")
            blob = requests.get(url, timeout=300).content
            res["bytes"] = len(blob)
            res["is_mp4"] = len(blob) > 12 and blob[4:8] == b"ftyp"
            if res["is_mp4"]:
                OUT.mkdir(parents=True, exist_ok=True)
                dest = OUT / "PROVEN_alibaba_wan2.7-t2v_720p.mp4"
                dest.write_bytes(blob)
                res.update(verdict="PROVEN", reason="OK", detail=f"real mp4 -> {dest}")
                print(f"\n  *** PROVEN *** real mp4, {len(blob)} bytes")
                print(f"  saved: {dest}")
            else:
                res["reason"] = "NOT_MP4"
                res["detail"] = (f"{len(blob)} bytes but bytes[4:8] != 'ftyp' "
                                 f"(head hex {blob[:12].hex()})")
                print(f"  {res['detail']}")
except Exception as exc:
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["reason"] = "TRANSPORT"
    res["detail"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    print(f"\nTRANSPORT after {res['elapsed_s']}s: {res['detail']}")

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "alibaba_720p_attempt.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(f"\nverdict: {res['verdict']} ({res['reason']})")

# Fold the answer into the accumulated sweep results so the matrix reflects it.
sw = OUT / "sweep_all_results.json"
if sw.exists():
    d = json.loads(sw.read_text(encoding="utf-8"))
    rows = {x["model"]: x for x in d.get("results", [])}
    rows[MODEL] = {"provider": "alibaba", "model": MODEL, "conn_status": "active", "duration": 5,
                   "http": res["http"], "elapsed_s": res["elapsed_s"], "bytes": res["bytes"],
                   "is_mp4": res["is_mp4"], "verdict": res["verdict"], "reason": res["reason"],
                   "detail": res["detail"], "saved": None}
    d["results"] = list(rows.values())
    sw.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"merged into {sw}")
