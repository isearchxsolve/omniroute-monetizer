#!/usr/bin/env python3
"""
OmniRoute State Backup (production, scheduled daily).

Backs up the runtime state required to recover OmniRoute and its automation:
  - C:\\Users\\Admin\\.omniroute\\storage.sqlite (+ -wal / -shm if present)
  - repo state/ (excluding heavy browser_profile/ blobs; keeps storage_state.json)
  - state/generated_keys.json, state/release_watch.json, state/omniroute_password.bin

Restores are documented in docs/OPS_RUNBOOK.md (stop service -> restore files ->
start service; admin step is user-run per AGENTS.md anti-pattern #8).

Usage:
  python backup_state.py [--backup-dir d:\\omniroute-backups] [--retain 14]
  .bat wrapper scheduled via schtasks daily.

Output: logs/backup.log + <backup-dir>/<date>/...
Exit:   0 = success | 1 = partial failure (some file missing) | 2 = fatal
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_DIR = PROJECT_ROOT / "state"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BACKUP_DIR = Path(r"d:\omniroute-backups")
OMNIROUTE_DATA = Path(r"C:\Users\Admin\.omniroute")

BACKUP_LOG = LOG_DIR / "backup.log"

# state/ entries to copy; browser_profile/ is copied at reduced depth (storage_state.json only)
STATE_INCLUDE = ["*.json", "*.bin"]
STATE_DEEP_DIRS = []  # e.g. ["dom_recon"] if desired
BROWSER_PROFILE_KEEP = ["storage_state.json"]


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(BACKUP_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def backup_sqlite(dest: Path) -> list[str]:
    copied = []
    if not OMNIROUTE_DATA.exists():
        log(f"WARN: OmniRoute data dir not found: {OMNIROUTE_DATA}")
        return copied
    for name in ("storage.sqlite", "storage.sqlite-wal", "storage.sqlite-shm"):
        src = OMNIROUTE_DATA / name
        if src.exists():
            try:
                shutil.copy2(src, dest / name)
                copied.append(name)
            except Exception as e:
                log(f"ERROR copying {name}: {e}")
    return copied


def backup_state(dest: Path) -> list[str]:
    copied = []
    for pattern in STATE_INCLUDE:
        for src in STATE_DIR.glob(pattern):
            try:
                shutil.copy2(src, dest / src.name)
                copied.append(f"state/{src.name}")
            except Exception as e:
                log(f"ERROR copying state/{src.name}: {e}")
    # browser profile storage_state.json only
    ss = STATE_DIR / "browser_profile" / "storage_state.json"
    if ss.exists():
        bd = dest / "browser_profile"
        bd.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(ss, bd / "storage_state.json")
            copied.append("state/browser_profile/storage_state.json")
        except Exception as e:
            log(f"ERROR copying storage_state.json: {e}")
    return copied


def prune(dest_root: Path, retain: int) -> None:
    dirs = sorted([d for d in dest_root.iterdir() if d.is_dir()])
    for old in dirs[:-retain]:
        try:
            shutil.rmtree(old)
            log(f"pruned old backup: {old.name}")
        except Exception as e:
            log(f"WARN: could not prune {old}: {e}")


def main() -> int:
    ap = argparse.ArgumentParser(description="OmniRoute state backup")
    ap.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    ap.add_argument("--retain", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true", help="list what would be copied, copy nothing")
    args = ap.parse_args()

    date_str = dt.datetime.now().strftime("%Y%m%d")
    dest = args.backup_dir / date_str
    log(f"=== BACKUP start -> {dest} (retain {args.retain}) ===")
    if args.dry_run:
        log("dry-run: would copy sqlite files, state/*.json, state/*.bin, storage_state.json")
        return 0

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"FATAL: cannot create backup dir: {e}")
        return 2

    failures = []
    db = backup_sqlite(dest)
    st = backup_state(dest)
    if not db and not OMNIROUTE_DATA.exists():
        failures.append("storage.sqlite (OmniRoute data dir absent)")
    if not st:
        failures.append("state files (none copied)")

    # manifest
    manifest = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "dest": str(dest),
        "sqlite_files": db,
        "state_files": st,
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"backup complete: {len(db)} sqlite files, {len(st)} state files")

    prune(args.backup_dir, args.retain)

    if failures:
        for f in failures:
            log(f"WARN: {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
