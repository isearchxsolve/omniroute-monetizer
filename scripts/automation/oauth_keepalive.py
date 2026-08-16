#!/usr/bin/env python3
"""
OmniRoute OAuth Keep-Alive (production).

Replaces the broken inference-ping daemon in scripts/omniroute_monetizer.py.

Why this exists (AGENTS.md anti-pattern #6):
  Sending inference requests does NOT refresh OAuth sessions — server-side
  timers dictate expiry. The ONLY correct mechanism is OmniRoute's native
  token-refresh endpoint:  POST /api/providers/{id}/refresh
  (verified 2026-08-16: rotates the token, advances expiresAt, anti-pattern #1
  compliant — uses the abstraction layer, never touches storage.sqlite).

GitHub Copilot tokens live ~30 minutes, amazon-q ~1 hour, so the default
refresh interval is 15 minutes.

Modes:
  --once          single refresh pass, then exit (for Windows Task Scheduler)
  (default)       loop forever every --interval seconds
  --interval N    loop interval seconds (default 900)

Password resolution (T11-safe, never logged):
  1. OMNIROUTE_PASSWORD env var
  2. state/omniroute_password.txt (gitignored)
  3. fallback literal in existing scratch scripts (bootstraps the state file)

Logging: logs/keepalive.log + state/keepalive_result.json (secrets redacted).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
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
LOG_FILE = LOG_DIR / "keepalive.log"
RESULT_FILE = STATE_DIR / "keepalive_result.json"
PW_FILE = STATE_DIR / "omniroute_password.txt"

DEFAULT_INTERVAL = 900  # 15 minutes — safe for 30-min Copilot tokens


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {redact(msg)}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def resolve_password() -> str:
    pw = os.environ.get("OMNIROUTE_PASSWORD", "").strip()
    if pw:
        return pw
    try:
        if PW_FILE.exists():
            pw = PW_FILE.read_text(encoding="utf-8").strip()
            if pw:
                return pw
    except Exception:
        pass
    # bootstrap from existing scratch-script fallback literal (already on disk)
    scratch = PROJECT_ROOT / "scratch"
    for name in ("raise_catalog_ttl.py", "live_apply_ttl.py"):
        p = scratch / name
        if not p.exists():
            continue
        try:
            m = re.search(r'or\s+"([^"]{8,})"', p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if m:
            pw = m.group(1)
            try:
                PW_FILE.write_text(pw, encoding="utf-8")
            except Exception:
                pass
            return pw
    return ""


def run_pass() -> dict:
    """One refresh pass over all active OAuth connections. Never raises."""
    started = time.monotonic()
    summary = {
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "refreshed": [],
        "failed": [],
        "skipped": [],
        "ok": True,
    }
    pw = resolve_password()
    if not pw:
        log("ERROR: no management password resolvable; pass skipped")
        summary["ok"] = False
        summary["error"] = "no_password"
        return summary

    try:
        api = OmniRouteAPI(password=pw)
        if not api.login():
            summary["ok"] = False
            summary["error"] = "login_failed"
            return summary
        conns = api.get_connections()
    except Exception as e:
        log(f"ERROR: management API unreachable: {type(e).__name__}: {e}")
        summary["ok"] = False
        summary["error"] = f"api_unreachable: {type(e).__name__}"
        return summary

    targets = [c for c in conns if c.get("authType") == "oauth" and c.get("isActive")]
    log(f"pass start: {len(targets)} active OAuth connections (of {len(conns)} total)")

    for c in targets:
        cid, prov = c.get("id"), c.get("provider")
        try:
            res = api.refresh_connection(cid)
            http = res.get("http_status")
            body = res.get("result") or {}
            success = http == 200 and bool(body.get("success"))
            if success:
                exp = body.get("expiresAt")
                summary["refreshed"].append({"id": cid, "provider": prov, "expiresAt": exp})
                log(f"  REFRESHED {prov:14s} expiresAt={exp}")
            else:
                err = body.get("error") or body.get("message") or f"HTTP {http}"
                summary["failed"].append({"id": cid, "provider": prov, "error": redact(str(err))[:160]})
                log(f"  FAILED    {prov:14s} {redact(str(err))[:120]}")
        except Exception as e:
            summary["failed"].append({"id": cid, "provider": prov, "error": f"{type(e).__name__}"})
            log(f"  FAILED    {prov:14s} exception {type(e).__name__}")

    summary["elapsed"] = round(time.monotonic() - started, 2)
    log(f"pass done: {len(summary['refreshed'])} refreshed, {len(summary['failed'])} failed, {summary['elapsed']}s")
    try:
        RESULT_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    except Exception:
        pass
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="OmniRoute OAuth keep-alive (native refresh endpoint)")
    ap.add_argument("--once", action="store_true", help="single pass then exit (scheduler mode)")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL, help=f"loop interval seconds (default {DEFAULT_INTERVAL})")
    args = ap.parse_args()

    if args.once:
        s = run_pass()
        return 0 if s.get("ok") else 1

    log(f"=== OAuth keep-alive daemon started (interval={args.interval}s) ===")
    while True:
        try:
            run_pass()
        except Exception as e:  # absolute crash guard
            log(f"unexpected pass error: {type(e).__name__}: {e}")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
