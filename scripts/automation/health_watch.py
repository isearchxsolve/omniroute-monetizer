#!/usr/bin/env python3
"""
OmniRoute Health Watch (production, single-pass).

Scheduled single-pass provider health check for Windows Task Scheduler.
Runs a full test pass over all active connections via POST /api/providers/{id}/test,
writes state/health_log.json (redacted), and exits non-zero if >= 3 connections
fail (so the scheduler / monitoring can alert).

Why single-pass instead of the ProviderHealthChecker daemon:
  The daemon holds its own thread + internal consecutive-failure state; a
  scheduled wrapper must be crash-guarded and stateless per run. This script
  reuses OmniRouteAPI (abstraction layer only — anti-pattern #1 compliant).

Password resolution: OMNIROUTE_PASSWORD env -> DPAPI vault -> legacy state file
(delegates to omniroute_api.get_password, never logs secrets).

Usage:
  python health_watch.py [--threshold 3] [--timeout 20]
  .bat wrapper scheduled via schtasks every 15 minutes.

Output: state/health_log.json
Exit:   0 = healthy (< threshold failures) | 1 = too many failures | 2 = error
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, redact  # noqa: E402

STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"
STATE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
HEALTH_LOG = STATE_DIR / "health_log.json"
WATCH_LOG = LOG_DIR / "health_watch.log"


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redact(msg)}"
    print(line, flush=True)
    try:
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="OmniRoute single-pass health watch")
    ap.add_argument("--threshold", type=int, default=3,
                    help="exit non-zero if this many connections fail (default 3)")
    ap.add_argument("--timeout", type=int, default=20,
                    help="per-connection test timeout seconds (default 20)")
    ap.add_argument("--quiet", action="store_true", help="suppress per-connection output")
    args = ap.parse_args()

    started = time.monotonic()
    log("=== HEALTH WATCH pass start ===")
    try:
        api = OmniRouteAPI()
        if not api.login():
            log("ERROR: management login failed (check OMNIROUTE_PASSWORD / DPAPI vault)")
            return 2
        conns = api.get_connections()
    except Exception as e:
        log(f"ERROR: management API unreachable: {type(e).__name__}: {e}")
        return 2

    active = [c for c in conns if c.get("isActive")]
    results = []
    failed = 0
    for c in active:
        cid, prov = c.get("id"), c.get("provider", "?")
        res = api.test_connection(cid)
        http = res.get("http_status")
        body = res.get("result") or {}
        valid = bool(body.get("valid")) if isinstance(body, dict) else False
        latency = (body.get("latencyMs") if body.get("latencyMs") is not None else body.get("latency")) if isinstance(body, dict) else None
        ok = http == 200 and valid
        if not ok:
            failed += 1
        results.append({
            "id": cid,
            "provider": prov,
            "ok": ok,
            "http": http,
            "latency": latency,
            "error": redact(str(body.get("error") or body.get("message") or ""))[:160] if not ok else "",
        })
        if not args.quiet:
            status = "OK " if ok else "FAIL"
            log(f"  [{status}] {prov:14s} http={http} latency={latency}")

    elapsed = round(time.monotonic() - started, 2)
    payload = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "tested": len(active),
        "failed": failed,
        "threshold": args.threshold,
        "elapsed": elapsed,
        "connections": results,
    }
    try:
        HEALTH_LOG.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"WARN: could not write {HEALTH_LOG}: {e}")

    log(f"pass done: {len(active)} tested, {failed} failed, {elapsed}s")
    if failed >= args.threshold:
        log(f"ALERT: {failed} connections failed (threshold {args.threshold})")
        return 1
    log("HEALTH WATCH pass OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
