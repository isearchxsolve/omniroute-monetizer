#!/usr/bin/env python3
"""
Fix P4: Residual /v1/models latency probe.

Purpose:
  Explain the gap between ~24ms warm cache hits and ~2.05s steady-state reads
  (POST_AUDIT_GAPS P4). Runs 20 sequential GET /v1/models at 10s spacing and
  records p50/p95/max plus HTTP status, with and without Authorization.

Output:
  state/residual_latency_report.json (redacted)

Ground rules:
  - Read-only GET; never restarts the service.
  - No secrets logged.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import BASE_URL, V1_URL, get_api_key, redact, save_json, log

SPACING_S = 10
SAMPLES = 20


def _probe_once(headers: Dict[str, str]) -> Dict[str, Any]:
    start = time.monotonic()
    try:
        r = __import__("requests").get(f"{V1_URL}/models", headers=headers, timeout=120)
        elapsed = round(time.monotonic() - start, 3)
        n = 0
        try:
            data = r.json()
            n = len(data.get("data", [])) if isinstance(data, dict) else 0
        except Exception:
            n = -1
        return {"http": r.status_code, "latency_s": elapsed, "models": n}
    except Exception as e:
        return {"http": None, "latency_s": round(time.monotonic() - start, 3),
                "models": None, "error": f"{type(e).__name__}: {e}"}


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"min": None, "p50": None, "p95": None, "max": None, "mean": None}
    return {
        "min": round(min(values), 3),
        "p50": round(statistics.median(values), 3),
        "p95": round(sorted(values)[int(len(values) * 0.95) - 1], 3),
        "max": round(max(values), 3),
        "mean": round(statistics.mean(values), 3),
    }


def run_probe(base: str = BASE_URL, samples: int = SAMPLES, spacing: float = SPACING_S,
              dry_run: bool = False) -> Dict[str, Any]:
    key = get_api_key()
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    log(f"P4 probe: {samples} GET /v1/models at {spacing}s spacing "
        f"(auth={'yes' if headers else 'no'})")
    if dry_run:
        log("dry-run: skipping live requests", "skip")
        return {"dry_run": True, "base": redact(base)}

    samples_list: List[Dict[str, Any]] = []
    for i in range(samples):
        s = _probe_once(headers)
        s["index"] = i
        samples_list.append(s)
        flag = "SLOW" if (s.get("latency_s") or 0) > 5 else "ok"
        log(f"  probe {i:02d}: HTTP {s.get('http')} {s.get('latency_s')}s "
            f"({s.get('models')} models) {flag}", "warn" if flag == "SLOW" else "info")
        if i < samples - 1:
            time.sleep(spacing)

    lat = [s["latency_s"] for s in samples_list if s.get("http") == 200]
    slow = [s for s in samples_list if (s.get("latency_s") or 0) > 5]

    conclusion = "UNKNOWN"
    if len(lat) >= 3:
        p50 = statistics.median(lat)
        if p50 > 1.0:
            conclusion = "STEADY_STATE_IS_HARDWARE_OR_PER_REQUEST_HOG"
        elif p50 < 0.1:
            conclusion = "WARM_CACHE_PREVAILS"
        else:
            conclusion = "MIXED"
    if slow:
        conclusion += "; PERIODIC_STALLS_DETECTED"

    report = {
        "timestamp": dt.datetime.now().isoformat(),
        "base": redact(base),
        "auth_header": bool(headers),
        "spacing_s": spacing,
        "samples": samples_list,
        "stats": {
            "200_only": _stats(lat),
            "all": _stats([s["latency_s"] for s in samples_list]),
        },
        "slow_count_gt5s": len(slow),
        "http_statuses": {str(s.get("http")): sum(1 for x in samples_list if x.get("http") == s.get("http"))
                          for s in samples_list},
        "conclusion": conclusion,
    }
    path = save_json("residual_latency_report.json", report)
    log(f"Report saved: {path}", "ok")
    log(f"CONCLUSION: {conclusion}", "warn" if "STALL" in conclusion else "ok")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P4 residual /v1/models latency probe")
    parser.add_argument("--samples", type=int, default=SAMPLES)
    parser.add_argument("--spacing", type=float, default=SPACING_S)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_probe(samples=args.samples, spacing=args.spacing, dry_run=args.dry_run)
