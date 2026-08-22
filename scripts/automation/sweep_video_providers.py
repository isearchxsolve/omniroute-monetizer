#!/usr/bin/env python3
"""sweep_video_providers.py -- try one text-to-video model on EVERY connected video provider.

Why this exists: on 2026-08-22 the video proof tested 4 providers out of the 15 in OmniRoute's
registry that carry video models, concluded "MONETIZER_BLOCKED -- no credit", and nearly stopped
there. Nine more were connected, active, and never tried. This sweeps the whole set so that
"blocked" is a measured statement about all of them, not about the first four.

It talks only to OmniRoute on localhost. It never reads or prints a provider key.

Reading the results:
    2xx + a real mp4        the provider WORKS. Money can flow through it.
    402/403/406/502+balance the key is fine, the account is empty. A money problem.
    404/400                 do NOT guess. Check the id against the full registry with
                            --check-ids before calling it a bad model name; an earlier pass
                            wrongly declared two real ids nonexistent by reading a truncated list.

An mp4 is only real if bytes[4:8] == b"ftyp". A 200 that returns an error page saved with a .mp4
name is NOT a proof, and this tool will say so.

Usage:
    python scripts/automation/sweep_video_providers.py                # sweep everything
    python scripts/automation/sweep_video_providers.py --free-only    # only providers with no key
    python scripts/automation/sweep_video_providers.py --check-ids    # verify ids exist, no calls
    python scripts/automation/sweep_video_providers.py --only llm7,pollinations
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:20128"
GEN_URL = f"{BASE}/v1/videos/generations"
CACHE = Path("state/model_cache.json")
OUT_DIR = Path("state/video_proofs")
REPORT = OUT_DIR / "sweep_report.json"

PROMPT = "a single red balloon drifting upward against a clear blue sky, slow steady shot"
GEN_TIMEOUT = 420
DOWNLOAD_TIMEOUT = 180

# One text-to-video candidate per provider. Duration carried per model because it is NOT global --
# grok-imagine rejects 5 and accepts 6/8/10, measured 2026-08-22.
CANDIDATES = [
    # provider,        model id,                                duration
    ("pollinations", "pollinations/seedance-2.0-fast",           5),
    ("llm7",         "llm7/seedance-2.0-fast",                  5),
    ("llm7",         "llm7/kling-v3.0-turbo",                   5),
    ("ainative",     "ainative/text-to-video-model",            5),
    ("alibaba",      "alibaba/happyhorse-1.1-t2v",              5),
    ("orcarouter",   "orcarouter/kling/kling-3-turbo",          5),
    ("vertex",       "vertex/veo-3.1-fast-generate-preview",    5),
    ("deepinfra",    "deepinfra/Pixverse/Pixverse-T2V",         5),
    ("kie",          "kie/veo/veo-3-1-fast",                    6),
    ("segmind",      "segmind/kling-video-t2v",                 5),
]


def say(text: str) -> None:
    """Print without ever dying on a non-cp1252 character.

    Upstream providers return non-ASCII error text -- Alibaba's answers contain full-width CJK
    punctuation. On a Windows console (cp1252) a bare print() of that raises UnicodeEncodeError and
    kills the whole sweep mid-run, losing every result after it. Measured 2026-08-22.
    """
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(enc, errors="backslashreplace").decode(enc, errors="replace"))


def registry_ids() -> set[str]:
    if not CACHE.exists():
        return set()
    try:
        return {m["id"] for m in json.loads(CACHE.read_text(encoding="utf-8"))["models"]}
    except Exception:
        return set()


def find_url(obj):
    """Dig a media URL out of whatever shape the response takes."""
    if isinstance(obj, str):
        return obj if obj.startswith("http") else None
    if isinstance(obj, dict):
        for f in ("url", "video_url", "videoUrl", "output_url", "result_url"):
            v = obj.get(f)
            if isinstance(v, str) and v.startswith("http"):
                return v
        for v in obj.values():
            got = find_url(v)
            if got:
                return got
    if isinstance(obj, list):
        for v in obj:
            got = find_url(v)
            if got:
                return got
    return None


def attempt(provider: str, model: str, duration: int) -> dict:
    row = {"provider": provider, "model": model, "duration": duration,
           "http": None, "elapsed_s": None, "bytes": None, "is_mp4": False,
           "verdict": "NOT_PROVEN", "detail": "", "saved": None}
    t0 = time.time()
    try:
        r = requests.post(GEN_URL, json={"model": model, "prompt": PROMPT, "duration": duration},
                          timeout=GEN_TIMEOUT)
    except Exception as exc:
        row["detail"] = f"request failed: {type(exc).__name__}"
        row["elapsed_s"] = round(time.time() - t0, 1)
        return row
    row["http"] = r.status_code
    row["elapsed_s"] = round(time.time() - t0, 1)

    if r.status_code >= 400:
        row["detail"] = f"HTTP {r.status_code}: {r.text[:400]}"
        return row

    try:
        body = r.json()
    except Exception:
        row["detail"] = f"200 but body is not JSON: {r.text[:200]}"
        return row

    url = find_url(body)
    if not url:
        row["detail"] = f"200 but no media url in body: {json.dumps(body)[:300]}"
        return row

    try:
        dl = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    except Exception as exc:
        row["detail"] = f"got a url but download failed: {type(exc).__name__}"
        return row

    data = dl.content
    row["bytes"] = len(data)
    row["is_mp4"] = data[4:8] == b"ftyp"
    if row["is_mp4"]:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        safe = model.replace("/", "_").replace(":", "_")
        dest = OUT_DIR / f"{safe}_{duration}s.mp4"
        dest.write_bytes(data)
        row["saved"] = str(dest)
        row["verdict"] = "PROVEN"
        row["detail"] = "real mp4, ftyp magic bytes confirmed"
    else:
        row["detail"] = (f"downloaded {len(data)} bytes but bytes[4:8]={data[4:8]!r}, "
                         "not a real mp4 -- NOT a proof")
    return row


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated providers")
    ap.add_argument("--check-ids", action="store_true",
                    help="verify every candidate id exists in the registry, make no calls")
    args = ap.parse_args()

    todo = CANDIDATES
    if args.only:
        want = {s.strip().lower() for s in args.only.split(",") if s.strip()}
        todo = [c for c in CANDIDATES if c[0].lower() in want]
    if not todo:
        print("nothing selected")
        return 2

    ids = registry_ids()
    if ids:
        missing = [m for _, m, _ in todo if m not in ids]
        print(f"registry loaded: {len(ids)} ids. candidates missing from it: "
              f"{missing if missing else 'none'}")
    else:
        print("registry cache not readable -- cannot pre-check ids")
    if args.check_ids:
        return 0

    print("=" * 78)
    print("  VIDEO SWEEP -- one text-to-video model per connected provider")
    print("=" * 78)
    print(f"  targets : {len(todo)}")
    print("  note    : a working clip takes 35s-140s. Failures come back in seconds.")
    print("-" * 78)

    rows = []
    for provider, model, duration in todo:
        row = attempt(provider, model, duration)
        rows.append(row)
        tag = "[PROVEN]    " if row["verdict"] == "PROVEN" else "[NOT PROVEN]"
        say(f"{tag} {provider}  ({model})")
        say(f"    http={row['http']}  elapsed={row['elapsed_s']}s  "
            f"bytes={row['bytes']}  is_mp4={row['is_mp4']}")
        if row["detail"]:
            say(f"    {row['detail'][:300]}")
        if row["saved"]:
            say(f"    saved: {row['saved']}")
        print()

    proven = [r for r in rows if r["verdict"] == "PROVEN"]
    print("=" * 78)
    print(f"  PROVEN {len(proven)} of {len(rows)}: "
          f"{', '.join(r['provider'] for r in proven) if proven else 'none'}")
    print("=" * 78)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"prompt": PROMPT, "results": rows}, indent=2), encoding="utf-8")
    print(f"  report: {REPORT}")
    return 0 if proven else 1


if __name__ == "__main__":
    sys.exit(main())
