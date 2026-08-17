"""Inspect the 9 snapshot-newer emergentsh files before merging.

Prints size/mtime + unified diff (truncated) for each pair so we can decide
per-file merge direction with evidence, not blind mtime trust.
NOTE: snapshot copy-time is ~2026-08-06T04:3x — files with exactly that mtime
had their clock reset by the copy, so content must be inspected.
"""
import difflib
from datetime import datetime
from pathlib import Path

SNAP = Path(r"D:\god_ai\lasthelp\lasthelp\emergentsh")
LIVE = Path(r"C:\god_ai\emergentsh")

FILES = [
    "backend/app/api/projects.py",
    "backend/app/services/nim_client.py",
    "backend/code_generation.py",
    "backend/requirements.txt",
    "backend/tests/test_nim_client.py",
    "tests/test_nim_client.py",
    "src/ui/widgets/auth/auth_dialog.py",
    "neon_architect.py",
    "neon_architect_v4_7_mobile_env.py",
]

MAX_DIFF_LINES = 60

for rel in FILES:
    s = SNAP / rel
    l = LIVE / rel
    print("=" * 70)
    print(f"FILE: {rel}")
    if not s.exists() or not l.exists():
        print(f"  missing: snap={s.exists()} live={l.exists()}")
        continue
    sm, lm = s.stat().st_mtime, l.stat().st_mtime
    print(f"  snap: {s.stat().st_size}B  {datetime.fromtimestamp(sm).isoformat()}")
    print(f"  live: {l.stat().st_size}B  {datetime.fromtimestamp(lm).isoformat()}")
    try:
        st = s.read_text(encoding="utf-8", errors="replace").splitlines()
        lt = l.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        print(f"  read error: {e}")
        continue
    diff = list(difflib.unified_diff(lt, st, fromfile="LIVE", tofile="SNAPSHOT", lineterm=""))
    print(f"  diff lines: {len(diff)}")
    for line in diff[:MAX_DIFF_LINES]:
        print("  " + line[:200])
    if len(diff) > MAX_DIFF_LINES:
        print(f"  ... ({len(diff) - MAX_DIFF_LINES} more diff lines)")
