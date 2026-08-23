"""Prove Google Flow (Veo) video through OmniRoute -- the one route that has FREE credits.

WHY THIS SHOULD WORK (all measured 2026-08-23 from the build + the live connections):
  - POST /v1/videos/generations resolves googleflow -> antigravity for credentials
    (build: resolveVideoCredentialProvider = "googleflow"===e?"antigravity":e).
  - An antigravity connection for isearch.xsolve@gmail.com already exists: oauth, active,
    projectId=thematic-victory-39z5m, providerSpecificData carries the token + projectId.
  - The handler resolveFlowAccessToken = creds.accessToken ?? creds.apiKey, and
    resolveFlowProjectId = creds.projectId ?? providerSpecificData.projectId -- both are present.
  - It POSTs {baseUrl}/v1:generateVideo {sampleCount, aspectRatio, durationSeconds, project, model}
    with Authorization: Bearer <token>, then polls /v1:fetchOperation every 10s for up to 300s.
  - The signed-in Flow account shows 1050 credits + 50 free daily, so this spends FREE credit, not a
    paywall -- squarely inside the rules.

IMPORTANT: this handler HARDCODES a 300s poll ceiling (Date.now()+3e5) and does NOT read timeout_ms
from the body, unlike dashscope/novita. So veo-3.1-fast is the right pick -- the fastest model, the
best chance of finishing inside 5 minutes. If it 504s at ~300s the job may still be rendering
upstream; that would be an OmniRoute-patience problem, not a refusal, and would be reported as such.

ONE attempt per model. Only a downloaded file whose bytes[4:8]==b"ftyp" counts as proven.
Presigned result URLs are credential material: only host + byte count are ever printed or saved.
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
PROMPT = "a single red balloon drifting upward against a clear blue sky, slow steady shot"

# fast first -- most likely to finish inside the handler's hardcoded 300s poll window
MODEL = sys.argv[1] if len(sys.argv) > 1 else "googleflow/veo-3.1-fast-generate"

payload = {
    "model": MODEL,
    "prompt": PROMPT,
    "duration": 5,
    "aspect_ratio": "16:9",
    "n": 1,
    # sent for completeness though this handler ignores it (poll ceiling is hardcoded 300s):
    "timeout_ms": 300_000,
    "poll_interval_ms": 10_000,
}

print(f"POST {GEN_URL}")
print(f"  model   : {MODEL}")
print(f"  credit  : Google Flow account isearch.xsolve@gmail.com (1050 credits + 50 free daily)")
print(f"  note    : handler polls a HARDCODED 300s; veo-3.1-fast chosen to fit inside it")
print(f"  started : {time.strftime('%H:%M:%S')} local")
sys.stdout.flush()

res = {"model": MODEL, "http": None, "elapsed_s": None, "bytes": None, "is_mp4": False,
       "verdict": "NOT_PROVEN", "reason": "", "detail": ""}
t0 = time.time()
try:
    r = requests.post(GEN_URL, json=payload, timeout=360)
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["http"] = r.status_code
    print(f"\nHTTP {r.status_code} after {res['elapsed_s']}s")
    try:
        body = r.json()
    except Exception:
        body = r.text[:800]

    if r.status_code != 200:
        err = body.get("error") if isinstance(body, dict) else body
        msg = err.get("message") if isinstance(err, dict) else str(err)
        res["reason"] = f"HTTP_{r.status_code}"
        res["detail"] = str(msg)[:500]
        print(f"  {res['detail']}")
    else:
        data = body.get("data") if isinstance(body, dict) else None
        first = data[0] if isinstance(data, list) and data else {}
        url = None
        if isinstance(first, dict):
            url = first.get("url") or first.get("video_url") or first.get("videoUrl")
        b64 = first.get("b64_json") if isinstance(first, dict) else None
        if url:
            p = urlsplit(url)
            print(f"  video url on host {p.netloc} ({len(url)} chars, query hidden) -- downloading")
            blob = requests.get(url, timeout=300).content
        elif b64:
            import base64
            print(f"  inline b64_json artifact ({len(b64)} chars) -- decoding")
            blob = base64.b64decode(b64)
        else:
            blob = b""
            res["reason"] = "NO_ARTIFACT"
            res["detail"] = f"HTTP 200 but no url/b64; keys={sorted(body.keys()) if isinstance(body,dict) else type(body)}"
            print(f"  {res['detail']}")
        if blob:
            res["bytes"] = len(blob)
            res["is_mp4"] = len(blob) > 12 and blob[4:8] == b"ftyp"
            if res["is_mp4"]:
                OUT.mkdir(parents=True, exist_ok=True)
                dest = OUT / f"PROVEN_googleflow_{MODEL.split('/')[-1]}.mp4"
                dest.write_bytes(blob)
                res.update(verdict="PROVEN", reason="OK", detail=f"real mp4 -> {dest}")
                print(f"\n  *** PROVEN *** real mp4, {len(blob)} bytes")
                print(f"  saved: {dest}")
            else:
                res["reason"] = "NOT_MP4"
                res["detail"] = f"{len(blob)} bytes but bytes[4:8]!='ftyp' (head {blob[:12].hex()})"
                print(f"  {res['detail']}")
except Exception as exc:
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["reason"] = "TRANSPORT"
    res["detail"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    print(f"\nTRANSPORT after {res['elapsed_s']}s: {res['detail']}")

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "googleflow_attempt.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
print(f"\nverdict: {res['verdict']} ({res['reason']})")

# Fold into the accumulated sweep results.
sw = OUT / "sweep_all_results.json"
if sw.exists():
    d = json.loads(sw.read_text(encoding="utf-8"))
    rows = {x["model"]: x for x in d.get("results", [])}
    rows[MODEL] = {"provider": "googleflow", "model": MODEL, "conn_status": "active", "duration": 5,
                   "http": res["http"], "elapsed_s": res["elapsed_s"], "bytes": res["bytes"],
                   "is_mp4": res["is_mp4"], "verdict": res["verdict"], "reason": res["reason"],
                   "detail": res["detail"], "saved": res.get("detail") if res["is_mp4"] else None}
    d["results"] = list(rows.values())
    sw.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"merged into {sw}")
