"""
prove_video.py -- the only test that actually proves a video provider works.

A key that verifies is a CANDIDATE. A connection that exists is a CANDIDATE. Neither
proves the provider can make a video. This script asks OmniRoute for a real short clip,
downloads it, and checks the file really is an MP4 by reading its magic bytes.

Duration is per-model, not a global 5. See the comment on CANDIDATES.

Anything less than `bytes[4:8] == b"ftyp"` is not a pass, and this script will say so.

SECRETS: the returned media URL is presigned -- it is credential material. It is never
printed or written to disk in full. Only its host and byte length are reported.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import requests

BASE = "http://localhost:20128"
GEN_URL = f"{BASE}/v1/videos/generations"

# One text-to-video model per provider, with the duration that model actually accepts.
# Model ids measured from OmniRoute's registry 2026-08-22.
#
# DURATION IS PER-MODEL, NOT 5. PROVIDER_HANDOFF.md says "5s clips only"; that is wrong for
# grok-imagine, which answers "Value must be within the specified range" for 5 and below and
# succeeds at 6, 8 and 10 (all three measured 2026-08-22). Omitting duration also fails. So
# never assume a global duration -- carry the measured one per model.
CANDIDATES = [
    ("kie",     "kie/grok-imagine/text-to-video", 6),   # PROVEN 2026-08-22: real mp4, 471777 bytes
    ("segmind", "segmind/ltx-video-t2v",          5),
    ("novita",  "novita/wan-t2v",                 5),
    ("vertex",  "vertex/veo-3.0-fast-generate-001", 5),
]

PROMPT = "a single red balloon drifting upward against a clear blue sky, slow steady shot"
GEN_TIMEOUT = 420          # measured 35s (grok-imagine); leave headroom, never retry a 4xx
DOWNLOAD_TIMEOUT = 120
OUT_DIR = Path("state/video_proofs")


def safe_url(url: str) -> str:
    """Presigned URLs are credentials. Report only the host and path shape."""
    try:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}/...({len(url)} chars, query hidden)"
    except Exception:
        return f"<unparseable url, {len(url)} chars>"


def extract_url(body: dict) -> str | None:
    data = body.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            for field in ("url", "video_url", "videoUrl"):
                if first.get(field):
                    return str(first[field])
    for field in ("url", "video_url"):
        if body.get(field):
            return str(body[field])
    return None


def prove(provider: str, model: str, duration: int) -> dict:
    result = {
        "provider": provider,
        "model": model,
        "duration": duration,
        "generate_status": None,
        "elapsed_s": None,
        "media_url": None,
        "bytes": None,
        "is_mp4": False,
        "verdict": "NOT_PROVEN",
        "detail": "",
    }
    payload = {
        "model": model,
        "prompt": PROMPT,
        "duration": duration,
        "aspect_ratio": "16:9",
        "n": 1,
    }
    t0 = time.time()
    try:
        r = requests.post(GEN_URL, json=payload, timeout=GEN_TIMEOUT)
    except Exception as exc:
        result["elapsed_s"] = round(time.time() - t0, 1)
        result["detail"] = f"generate call failed: {type(exc).__name__}: {str(exc)[:160]}"
        return result

    result["elapsed_s"] = round(time.time() - t0, 1)
    result["generate_status"] = r.status_code

    try:
        body = r.json()
    except Exception:
        result["detail"] = f"HTTP {r.status_code} but body was not JSON: {r.text[:200]!r}"
        return result

    if r.status_code != 200:
        err = body.get("error")
        msg = err.get("message") if isinstance(err, dict) else (err or body)
        result["detail"] = f"HTTP {r.status_code}: {str(msg)[:240]}"
        return result

    url = extract_url(body)
    if not url:
        result["detail"] = (
            f"HTTP 200 but no media url in the response. "
            f"top-level fields: {sorted(body.keys())}"
        )
        return result

    result["media_url"] = safe_url(url)

    try:
        dl = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    except Exception as exc:
        result["detail"] = f"got a url but download failed: {type(exc).__name__}"
        return result

    if dl.status_code != 200:
        result["detail"] = f"got a url but download returned HTTP {dl.status_code}"
        return result

    blob = dl.content
    result["bytes"] = len(blob)
    result["is_mp4"] = len(blob) > 12 and blob[4:8] == b"ftyp"

    if not result["is_mp4"]:
        head = blob[:12].hex() if blob else ""
        result["detail"] = (
            f"downloaded {len(blob)} bytes but bytes[4:8] != 'ftyp' "
            f"(first 12 bytes hex: {head}) -- this is NOT an mp4"
        )
        return result

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{provider}_{model.replace('/', '_')}.mp4"
    out.write_bytes(blob)
    result["verdict"] = "PROVEN"
    result["detail"] = f"real mp4, {len(blob)} bytes, saved {out}"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="Prove video providers make real MP4 files.")
    ap.add_argument("--only", default="", help="comma-separated providers, e.g. kie,segmind")
    ap.add_argument("--serial", action="store_true", help="one at a time instead of together")
    args = ap.parse_args()

    targets = CANDIDATES
    if args.only:
        want = {s.strip() for s in args.only.split(",") if s.strip()}
        targets = [c for c in CANDIDATES if c[0] in want]
    if not targets:
        print("no matching providers")
        return 2

    print("=" * 78)
    print("  VIDEO PROOF -- one clip per provider, then check the magic bytes")
    print("=" * 78)
    print(f"  started : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  targets : {', '.join(p for p, _, _ in targets)}")
    print(f"  note    : measured 35s-140s per clip. Be patient.")
    print()

    if args.serial:
        results = [prove(p, m, d) for p, m, d in targets]
    else:
        # 3 workers max is the measured safe concurrency for this contract.
        with ThreadPoolExecutor(max_workers=min(3, len(targets))) as pool:
            results = list(pool.map(lambda c: prove(*c), targets))

    print("-" * 78)
    for r in results:
        tag = "[PROVEN] " if r["verdict"] == "PROVEN" else "[NOT PROVEN] "
        print(f"{tag}{r['provider']}  ({r['model']})")
        print(f"    http={r['generate_status']}  duration={r['duration']}s  "
              f"elapsed={r['elapsed_s']}s  bytes={r['bytes']}"
              f"  is_mp4={r['is_mp4']}")
        if r["media_url"]:
            print(f"    media: {r['media_url']}")
        if r["detail"]:
            print(f"    {r['detail']}")
        print()

    proven = [r for r in results if r["verdict"] == "PROVEN"]
    print("=" * 78)
    print(f"  PROVEN {len(proven)} of {len(results)}: "
          f"{', '.join(r['provider'] for r in proven) or 'none'}")
    print("=" * 78)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = OUT_DIR / "proof_report.json"
    report.write_text(json.dumps({
        "generated": datetime.now().isoformat(timespec="seconds"),
        "prompt": PROMPT,
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"  report: {report}")

    return 0 if proven else 1


if __name__ == "__main__":
    sys.exit(main())
