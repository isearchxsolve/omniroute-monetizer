"""Call api.segmind.com DIRECTLY to decode the errors OmniRoute truncates.

WHY THIS EXISTS -- measured 2026-08-23:
Through the gateway, all 5 segmind video routes failed and the upstream error body arrived
truncated to a single "{", so the failure was undiagnosable. OmniRoute builds the upstream URL as
    {baseUrl}/{model-id}   ->   https://api.segmind.com/v1/wan2.1-t2v
so a 404 is a REGISTRY BUG (that slug does not exist at segmind), while segmind documents
    406 Not Acceptable = insufficient credits
which is a paywall and must never be retried. This script proves which is which by reading the
real response body.

RULES HONOURED:
  - ONE request per route. No retries, no hammering.
  - The api key is never printed; only its length and last 4 characters.
  - A 406/402/credit answer is recorded and the provider is then left alone.

Read-only against our own state; the only writes are the JSON report.
"""
from __future__ import annotations

import json
import pathlib
import time

import requests

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
BASE = "https://api.segmind.com/v1"
OUT = ROOT / "state" / "video_proofs" / "segmind_direct_probe.json"

keys = json.loads((ROOT / "state" / "generated_keys.json").read_text(encoding="utf-8"))
entry = keys.get("segmind") or {}
key = entry.get("key") or ""
if not key:
    raise SystemExit("no segmind key in state/generated_keys.json -- nothing to probe")
print(f"using stored segmind key: len={len(key)}, ends ...{key[-4:]}")

reg = json.loads((ROOT / "state" / "video_registry_native.json").read_text(encoding="utf-8"))
models = [m["id"] for m in reg["segmind"]["models"]]

HEAD = {"x-api-key": key, "Content-Type": "application/json"}
BODY = {"prompt": "a single red balloon drifting upward against a clear blue sky",
        "negative_prompt": "blurry", "seed": 42}

results = []
print()
for mid in models:
    url = f"{BASE}/{mid}"
    t0 = time.time()
    try:
        r = requests.post(url, headers=HEAD, json=BODY, timeout=90)
        el = round(time.time() - t0, 1)
        ct = r.headers.get("content-type", "")
        # Media comes back as raw bytes; anything else is an error we want to read in full.
        if "json" in ct or "text" in ct or len(r.content) < 4000:
            body = r.text[:600]
        else:
            body = f"<binary {len(r.content)} bytes, content-type {ct}>"
        results.append({"model": mid, "url": url, "http": r.status_code,
                        "content_type": ct, "elapsed_s": el, "body": body,
                        "is_mp4": len(r.content) > 12 and r.content[4:8] == b"ftyp"})
        print(f"  {mid:<22} HTTP {r.status_code}  {el}s  ct={ct[:28]}")
        print(f"      {body[:320]}")
    except Exception as exc:
        el = round(time.time() - t0, 1)
        results.append({"model": mid, "url": url, "http": None, "elapsed_s": el,
                        "body": f"{type(exc).__name__}: {str(exc)[:200]}", "is_mp4": False})
        print(f"  {mid:<22} TRANSPORT {type(exc).__name__} after {el}s")
    print()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps({"base": BASE, "results": results}, indent=1), encoding="utf-8")

print("=" * 78)
codes = {}
for r in results:
    codes.setdefault(str(r["http"]), []).append(r["model"])
for c, ms in sorted(codes.items()):
    print(f"  HTTP {c}: {len(ms)}  {', '.join(ms)}")
mp4 = [r["model"] for r in results if r.get("is_mp4")]
print(f"  real mp4 returned: {len(mp4)}  {mp4}")
print(f"saved: {OUT}")
