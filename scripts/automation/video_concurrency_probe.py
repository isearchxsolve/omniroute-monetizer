#!/usr/bin/env python3
"""
Measure how many video generations OmniRoute will run *concurrently* on one credential.

Why this matters more than raw latency
--------------------------------------
A 3-hour film is ~2,160 five-second shots. At the measured ~140s per clip, a sequential
Animator needs ~84 hours. Concurrency is the only lever available that costs nothing —
no new provider, no new key, no account top-up. If the single alibaba credential sustains
N parallel jobs, the wall-clock floor drops by ~N.

What we are actually testing is the *whole path*: OmniRoute's request handling, its
per-connection concurrency gate (`maxConcurrent`, currently null), and DashScope's own
per-key rate limit. Any of the three could serialise us, and only a real parallel run
distinguishes "N workers" from "N queued requests".

Reports per-request outcome plus the speedup versus running the same batch serially.
Never writes to OmniRoute.

Usage:
    python scripts/automation/video_concurrency_probe.py --n 4
    python scripts/automation/video_concurrency_probe.py --n 8 --model alibaba/happyhorse-1.1-t2v
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from omniroute_api import BASE_URL, LOGIN_TIMEOUT, OmniRouteAPI, redact, redact_url, save_json  # noqa: E402

DEFAULT_MODEL = "alibaba/wan2.7-t2v-2026-06-12"

# Distinct prompts so nothing can be served from a prompt-keyed cache upstream, which
# would make concurrency look free when it is not.
PROMPTS = [
    "A lone lighthouse on a storm-lashed cliff, waves exploding against black rock at dusk",
    "A neon-lit rain-slicked Tokyo alley, steam rising from a ramen stall, shallow depth of field",
    "An empty desert highway under a lightning storm, heat shimmer on the asphalt at dawn",
    "A slow overhead drift across an autumn forest canopy, mist between the trees, golden light",
    "A derelict space station corridor, dust motes drifting through a shaft of sunlight",
    "A fishing boat cutting through arctic fog, ice on the railings, pale grey morning",
    "A crowded 1920s ballroom seen from the balcony, chandeliers blazing, dancers swirling",
    "A single red poppy in a wind-blown wheat field, storm clouds gathering behind",
]


def one_request(session: requests.Session, model: str, prompt: str, duration: int,
                timeout: int, index: int) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        r = session.post(
            f"{BASE_URL}/v1/videos/generations",
            json={"model": model, "prompt": prompt, "duration": duration, "aspect_ratio": "16:9"},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
    except Exception as e:
        return {"i": index, "ok": False, "elapsed": round(time.monotonic() - started, 1),
                "status": None, "error": f"{type(e).__name__}: {e}"}

    elapsed = round(time.monotonic() - started, 1)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:400]}

    url = ""
    data = body.get("data") if isinstance(body, dict) else None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        url = str(data[0].get("url") or "")
    return {
        "i": index,
        "ok": r.status_code == 200 and bool(url),
        "status": r.status_code,
        "elapsed": elapsed,
        "url": redact_url(url) if url else "",
        "error": None if r.status_code == 200 else redact(str(body))[:300],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=4, help="number of concurrent requests")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--duration", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    api = OmniRouteAPI()
    resp = api.session.post(f"{api.api}/auth/login", json={"password": api._password},
                            timeout=LOGIN_TIMEOUT)
    if resp.status_code != 200:
        print(f"[-] management login failed: HTTP {resp.status_code}")
        return 2
    print(f"[+] management login OK")
    print(f"[*] firing {args.n} concurrent {args.duration}s requests at {args.model}\n")

    # A Session is not guaranteed thread-safe for concurrent use; give each worker its own.
    sessions = []
    for _ in range(args.n):
        s = requests.Session()
        s.cookies.update(api.session.cookies)
        sessions.append(s)

    wall_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.n) as pool:
        futures = [
            pool.submit(one_request, sessions[i], args.model,
                        PROMPTS[i % len(PROMPTS)], args.duration, args.timeout, i)
            for i in range(args.n)
        ]
        results = [f.result() for f in futures]
    wall = round(time.monotonic() - wall_start, 1)

    results.sort(key=lambda r: r["i"])
    for r in results:
        mark = "PASS" if r["ok"] else "FAIL"
        detail = r["url"][:70] if r["ok"] else (r["error"] or "")[:110]
        print(f"  [{mark}] req{r['i']}  HTTP {str(r['status']):5} {r['elapsed']:>6}s  {detail}")

    ok = [r for r in results if r["ok"]]
    lat = [r["elapsed"] for r in ok]
    serial_estimate = sum(lat)
    print(f"\n  succeeded      : {len(ok)}/{len(results)}")
    if lat:
        print(f"  latency        : min {min(lat)}s / median {statistics.median(lat)}s / max {max(lat)}s")
        print(f"  wall clock     : {wall}s")
        print(f"  serial estimate: {round(serial_estimate,1)}s (sum of the same {len(ok)} jobs)")
        print(f"  effective speedup: {round(serial_estimate / wall, 2)}x")
        print(f"  => sustained concurrency ~= {round(serial_estimate / wall, 2)} of {args.n} requested")

    path = save_json("video_concurrency_probe.json", {
        "model": args.model, "requested_concurrency": args.n, "duration": args.duration,
        "wall_seconds": wall, "serial_estimate_seconds": round(serial_estimate, 1),
        "speedup": round(serial_estimate / wall, 2) if wall else None,
        "succeeded": len(ok), "results": results,
    })
    print(f"\n[*] results -> {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
