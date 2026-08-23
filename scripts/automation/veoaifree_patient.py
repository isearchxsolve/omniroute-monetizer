"""One patient attempt at veoaifree-web -- the only zero-auth, non-local, handler-backed video route.

MEASURED 2026-08-23:
  veoaifree-web/veo       -> ReadTimeout at 422s, no HTTP status
  veoaifree-web/seedance  -> ReadTimeout at 422s, no HTTP status
The 422s was OUR client timeout, not the server refusing. veoaifree.com answers HEAD / in 3.9s so
the site is alive, and the handler passes `signal:null` to the executor -- no abort -- so an
unbounded server-side wait is exactly what a hang would look like. app.log contains zero lines for
this provider, so the only way to learn the outcome is to wait it out once.

This is ONE request, not hammering. A free web service that queues jobs may legitimately take
many minutes; we give it 25 and then stop asking.
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
REPORT = OUT / "veoaifree_patient.json"

MODEL = sys.argv[1] if len(sys.argv) > 1 else "veoaifree-web/veo"
TIMEOUT = int(sys.argv[2]) if len(sys.argv) > 2 else 1500      # 25 minutes

payload = {"model": MODEL, "prompt": "a single red balloon drifting upward against a clear blue sky,"
                                     " slow steady shot",
           "duration": 5, "aspect_ratio": "16:9", "n": 1}

print(f"POST {GEN_URL}")
print(f"  model   : {MODEL}")
print(f"  timeout : {TIMEOUT}s  (one attempt only)")
print(f"  started : {time.strftime('%H:%M:%S')} local")
sys.stdout.flush()

t0 = time.time()
res = {"model": MODEL, "timeout_s": TIMEOUT, "http": None, "elapsed_s": None,
       "verdict": "NOT_PROVEN", "reason": "", "detail": "", "bytes": None, "is_mp4": False}
try:
    r = requests.post(GEN_URL, json=payload, timeout=TIMEOUT)
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["http"] = r.status_code
    print(f"\nHTTP {r.status_code} after {res['elapsed_s']}s")
    try:
        body = r.json()
    except Exception:
        body = r.text[:800]
    if r.status_code != 200:
        res["reason"] = f"HTTP_{r.status_code}"
        res["detail"] = json.dumps(body)[:700] if isinstance(body, dict) else str(body)[:700]
        print(f"  body: {res['detail'][:500]}")
    else:
        # b64_json is what this handler is documented to require.
        data = body.get("data") if isinstance(body, dict) else None
        first = data[0] if isinstance(data, list) and data else {}
        blob = None
        if isinstance(first, dict) and first.get("b64_json"):
            import base64
            blob = base64.b64decode(first["b64_json"])
            res["detail"] = "artifact arrived inline as b64_json"
        elif isinstance(first, dict) and first.get("url"):
            u = str(first["url"])
            p = urlsplit(u)
            res["detail"] = f"url on host {p.netloc} ({len(u)} chars, query hidden); downloading"
            print(f"  {res['detail']}")
            blob = requests.get(u, timeout=300).content
        if blob is None:
            res["reason"] = "NO_ARTIFACT"
            res["detail"] = (f"HTTP 200 but no b64_json and no url; keys="
                             f"{sorted(body.keys()) if isinstance(body, dict) else type(body)}")
        else:
            res["bytes"] = len(blob)
            res["is_mp4"] = len(blob) > 12 and blob[4:8] == b"ftyp"
            if res["is_mp4"]:
                OUT.mkdir(parents=True, exist_ok=True)
                dest = OUT / f"PROVEN_{MODEL.replace('/', '_')}.mp4"
                dest.write_bytes(blob)
                res.update(verdict="PROVEN", reason="OK", detail=f"real mp4 -> {dest}")
                print(f"\n  *** PROVEN *** {len(blob)} bytes, saved {dest}")
            else:
                res["reason"] = "NOT_MP4"
                res["detail"] += (f" -- {len(blob)} bytes but bytes[4:8] != 'ftyp' "
                                  f"(head hex {blob[:12].hex()})")
except Exception as exc:
    res["elapsed_s"] = round(time.time() - t0, 1)
    res["reason"] = "TRANSPORT"
    res["detail"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    print(f"\nTRANSPORT {type(exc).__name__} after {res['elapsed_s']}s")
    print(f"  {res['detail']}")

OUT.mkdir(parents=True, exist_ok=True)
REPORT.write_text(json.dumps(res, indent=1), encoding="utf-8")
print(f"\nverdict: {res['verdict']} ({res['reason']})")
print(f"saved: {REPORT}")
