#!/usr/bin/env python3
"""
OmniRoute Acceptance Watch (production, scheduled).

Runs the full acceptance suite (acceptance_tests.py) on a schedule, writes a
summary markdown to state/acceptance_latest.md, and keeps the last 30 runs in
state/acceptance_history/. On regression (non-skip failures), appends a
MASTER_WORKLOG.md entry in the worklog's entry template so the audit trail
stays current without human intervention.

Usage:
  python acceptance_watch.py
  .bat wrapper scheduled via schtasks every 6 hours.

Output: state/acceptance_latest.md, state/acceptance_history/<ts>.json
Exit:   0 = no regressions | 1 = regressions detected
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"
HISTORY_DIR = STATE_DIR / "acceptance_history"
STATE_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

LATEST_MD = STATE_DIR / "acceptance_latest.md"
WATCH_LOG = LOG_DIR / "acceptance_watch.log"
KEEP_RUNS = 30


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def parse_results(text: str) -> dict:
    """Parse acceptance output into {test_id: {status, message}}."""
    results = {}
    for m in re.finditer(r"\[\s*(PASS|FAIL|SKIP)\s*\]\s*(T\d+):\s*(.*)", text):
        status, tid, msg = m.group(1), m.group(2), m.group(3)
        results[tid] = {"status": status, "message": msg}
    return results


def append_worklog_entry(failures: list) -> None:
    """Append a MASTER_WORKLOG entry on regression (respects entry template)."""
    worklog = PROJECT_ROOT / "MASTER_WORKLOG.md"
    if not worklog.exists():
        return
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    failing = ", ".join(f"{t}({r['status']})" for t, r in failures)
    entry = (
        f"\n### [{now}] #AUTO — ACCEPTANCE REGRESSION DETECTED\n"
        f"**What:** Scheduled acceptance watch detected failures.\n"
        f"**Why:** Scheduled `acceptance_watch.py` run failed; see `state/acceptance_latest.md`.\n"
        f"**Findings:** Failing tests: {failing}.\n"
        f"**Status:** ⚠️ REGRESSION — review `state/acceptance_history/` for detail.\n"
    )
    try:
        with open(worklog, "a", encoding="utf-8") as f:
            f.write(entry)
        log("Appended regression entry to MASTER_WORKLOG.md")
    except Exception as e:
        log(f"WARN: could not append worklog entry: {e}")


def main() -> int:
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    log("=== ACCEPTANCE WATCH run start ===")
    suite_path = PROJECT_ROOT / "acceptance_tests.py"
    proc = subprocess.run(
        [sys.executable, str(suite_path)],
        capture_output=True, text=True, timeout=1800,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    results = parse_results(text)

    failed = [r for r in results.items() if r[1]["status"] == "FAIL"]
    skipped = [r for r in results.items() if r[1]["status"] == "SKIP"]
    verdict = proc.returncode
    ready = "MONETIZER_READY" in text

    summary = {
        "timestamp": ts,
        "returncode": proc.returncode,
        "ready": ready,
        "passed": sum(1 for r in results.values() if r["status"] == "PASS"),
        "failed": len(failed),
        "skipped": len(skipped),
        "failures": failed,
        "skips": skipped,
    }

    history_file = HISTORY_DIR / f"{ts}.json"
    history_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # prune to last KEEP_RUNS
    runs = sorted(HISTORY_DIR.glob("*.json"))
    for old in runs[:-KEEP_RUNS]:
        try:
            old.unlink()
        except Exception:
            pass

    md = [
        f"# Acceptance Watch — {ts}",
        "",
        f"- **Ready:** {'YES' if ready else 'NO'}",
        f"- **Passed / Failed / Skipped:** {summary['passed']} / {summary['failed']} / {summary['skipped']}",
        f"- **Return code:** {verdict}",
        "",
        "## Failures",
    ]
    if failed:
        for tid, r in failed:
            md.append(f"- **{tid}**: {r['message']}")
    else:
        md.append("- none")
    md.append("")
    md.append("## Skips")
    if skipped:
        for tid, r in skipped:
            md.append(f"- {tid}: {r['message']}")
    else:
        md.append("- none")

    LATEST_MD.write_text("\n".join(md), encoding="utf-8")

    if failed:
        log(f"FAIL: {len(failed)} failures ({', '.join(t for t, _ in failed)})")
        append_worklog_entry(failed)
        return 1
    log(f"OK: all {summary['passed']} tests passed, {len(skipped)} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
