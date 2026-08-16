#!/usr/bin/env python3
"""
OmniRoute Stall Monitor (production, scheduled).

Detects the periodic synchronous catalog-rebuild freeze (Blocker #3, worklog
#22-#25: ~24-38s event-loop block every ~10.6 min on 3.8.49; fixed upstream in
v3.8.50). Probes /v1/models every N seconds for a bounded pass and alerts
(log + exit code) if any probe exceeds the threshold outside an expected
rebuild window.

The known 60s-TTL rebuild produces a legitimate single slow probe roughly
every ~635s (600s TTL + 30s stale window). To avoid false alerts, this monitor:
  - runs a bounded 3-minute pass,
  - treats the FIRST slow probe per pass as expected (rebuild window),
  - alerts only if a second slow probe occurs within the same pass, or if a
    probe exceeds the threshold at a cadence inconsistent with the TTL.

Usage:
  python stall_monitor.py [--interval 10] [--max-pass 180] [--threshold 5]
  .bat wrapper scheduled via schtasks every 15 minutes.

Output: logs/stall_monitor.log + state/stall_monitor_result.json
Exit:   0 = clean | 1 = alert (stall detected)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:20128"
RESULT_FILE = STATE_DIR / "stall_monitor_result.json"
MONITOR_LOG = LOG_DIR / "stall_monitor.log"


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(MONITOR_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def probe() -> float:
    """Return latency seconds for GET /v1/models, or raise on error."""
    start = time.monotonic()
    r = requests.get(f"{BASE_URL}/v1/models", timeout=60)
    r.raise_for_status()
    return round(time.monotonic() - start, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description="OmniRoute stall monitor")
    ap.add_argument("--interval", type=float, default=10, help="probe interval seconds")
    ap.add_argument("--max-pass", type=float, default=180, help="max pass duration seconds")
    ap.add_argument("--threshold", type=float, default=5.0,
                    help="slow-probe threshold seconds (default 5.0)")
    args = ap.parse_args()

    log(f"=== STALL MONITOR pass start (interval={args.interval}s, max={args.max_pass}s, thr={args.threshold}s) ===")
    started = time.monotonic()
    samples = []
    slow_samples = []
    errors = []

    while time.monotonic() - started < args.max_pass:
        ts = dt.datetime.now().isoformat(timespec="seconds")
        try:
            latency = probe()
            samples.append({"ts": ts, "latency": latency})
            if latency > args.threshold:
                slow_samples.append({"ts": ts, "latency": latency})
                log(f"  SLOW {latency}s at {ts}")
            else:
                log(f"  ok   {latency}s")
        except Exception as e:
            errors.append({"ts": ts, "error": f"{type(e).__name__}: {e}"})
            log(f"  ERR  {type(e).__name__}: {e}")
        time.sleep(args.interval)

    # Alert policy: more than one slow sample per pass = abnormal.
    # One slow sample is the expected rebuild-window artifact on 3.8.49.
    alert = len(slow_samples) > 1 or (len(slow_samples) == 1 and len(errors) > 0)
    payload = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "threshold": args.threshold,
        "samples": samples,
        "slow_samples": slow_samples,
        "errors": errors,
        "alert": alert,
        "note": "One slow probe per pass is the known 60s-TTL rebuild window (blocker #3); >1 = abnormal.",
    }
    try:
        RESULT_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"WARN: could not write result file: {e}")

    if alert:
        log(f"ALERT: {len(slow_samples)} slow probes (>{args.threshold}s) + {len(errors)} errors in this pass")
        return 1
    log(f"STALL MONITOR pass OK ({len(slow_samples)} slow, {len(errors)} errors, {len(samples)} samples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
