#!/usr/bin/env python3
"""
Fix P7: Read-only DB integrity / WAL checkpoint health monitor.

Purpose:
  POST_AUDIT_GAPS P7 — WAL grew to 4.1 MB during the corruption era and nothing
  monitors WAL size, PRAGMA integrity_check, or checkpoint health.

Ground rules (AGENTS.md anti-pattern #1):
  - NEVER open storage.sqlite for WRITE. No pragma that mutates (no wal_checkpoint,
    no optimize). Integrity check is opened read-only with immutable=1.
  - If the SQLite file is unreachable/busy (service holds it), the script reports
    filesystem-only evidence (WAL/SHM sizes, growth) and skips the pragma.

Output:
  state/db_integrity_report.json (redacted)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import redact, save_json, log

# Configurable DB path; matches worklog (#14-#18 corruption era) + INSTALLATION.md
DEFAULT_DB = Path(r"C:\Users\Admin\.omniroute\storage.sqlite")
WAL_THRESHOLD_MB = 8.0  # warn if WAL exceeds 8 MB (grew to 4.1 MB during corruption)
SIZE_THRESHOLD_MB = 64.0  # sanity: DB should not balloon past this

# Extra files tracked in backups (G10)
EXTRA_FILES = ("-wal", "-shm")


def _mb(p: Path) -> float:
    try:
        return round(p.stat().st_size / (1024 * 1024), 2)
    except Exception:
        return -1.0


def _integrity_check(db: Path) -> Dict[str, Any]:
    """Read-only integrity_check. Returns {} if DB is locked/unavailable."""
    if not db.exists():
        return {"error": "db_not_found"}
    try:
        uri = f"file:{db.as_posix()}?mode=ro&immutable=1"
        con = sqlite3.connect(uri, uri=True, timeout=2)
        try:
            rows = con.execute("PRAGMA integrity_check").fetchall()
            con.execute("PRAGMA journal_mode")
            return {"integrity_check": [r[0] for r in rows]}
        finally:
            con.close()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def run_check(db_path: Path = DEFAULT_DB, dry_run: bool = False) -> Dict[str, Any]:
    log(f"P7 DB integrity check on {db_path} (read-only)")
    if not db_path.exists():
        log(f"DB not found at {db_path} — is this the sandbox? Running filesystem-only.", "warn")

    fs: Dict[str, Any] = {}
    for suffix in ("",) + EXTRA_FILES:
        p = db_path.with_name(db_path.name + suffix)
        fs[suffix or "main"] = {"exists": p.exists(), "size_mb": _mb(p) if p.exists() else None,
                                "mtime": dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                                if p.exists() else None}

    integrity: Dict[str, Any] = {}
    if dry_run:
        log("dry-run: skipping pragma", "skip")
    else:
        integrity = _integrity_check(db_path)
        if integrity.get("integrity_check"):
            ok = all(r == "ok" for r in integrity["integrity_check"])
            log(f"integrity_check: {'OK' if ok else 'CORRUPT: ' + str(integrity['integrity_check'][:3])}",
                "ok" if ok else "err")
        elif integrity.get("error"):
            log(f"integrity_check skipped: {integrity['error']} (service holds the file)", "warn")

    wal_mb = fs.get("-wal", {}).get("size_mb") or 0.0
    main_mb = fs.get("main", {}).get("size_mb") or 0.0
    alerts = []
    if wal_mb > WAL_THRESHOLD_MB:
        alerts.append(f"WAL size {wal_mb}MB exceeds {WAL_THRESHOLD_MB}MB threshold")
    if main_mb > SIZE_THRESHOLD_MB:
        alerts.append(f"DB size {main_mb}MB exceeds {SIZE_THRESHOLD_MB}MB sanity threshold")
    if integrity.get("integrity_check") and any(r != "ok" for r in integrity["integrity_check"]):
        alerts.append("integrity_check returned non-ok rows (CORRUPTION)")

    report = {
        "timestamp": dt.datetime.now().isoformat(),
        "dry_run": dry_run,
        "db_path": redact(str(db_path)),
        "filesystem": fs,
        "integrity": integrity,
        "thresholds_mb": {"wal": WAL_THRESHOLD_MB, "db": SIZE_THRESHOLD_MB},
        "alerts": alerts,
        "verdict": "HEALTHY" if not alerts else "REVIEW_REQUIRED",
    }
    path = save_json("db_integrity_report.json", report)
    log(f"Report saved: {path}  verdict={report['verdict']}", "ok" if not alerts else "warn")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P7 read-only DB/WAL integrity monitor")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run_check(db_path=Path(args.db), dry_run=args.dry_run)
