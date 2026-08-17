"""Merge the genuine ases_v3_1 gaps: snapshot-newer auth.py + test_smoke_gate.py.

Live auth.py is 2026-06-20, snapshot is 2026-08-09 -> genuine lost patch.
Live has NOTHING newer for these two files, so merge is safe.
(neon_architect.py excluded: giant shared generated artifact, not ases-specific.)
Backup before overwrite per AGENTS.md.
"""
import shutil
from datetime import datetime
from pathlib import Path

LASTHELP = Path(r"D:\god_ai\lasthelp\lasthelp\ases_v3_1")
LIVE = Path(r"C:\god_ai\ases_v3_1")
BACKUP = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue\pre_merge_backups\ases_v3_1")

FILES = ["agent_service/auth.py", "tests/test_smoke_gate.py"]
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

for rel in FILES:
    snap_f = LASTHELP / rel
    live_f = LIVE / rel
    if not snap_f.exists():
        print(f"[missing-snap] {rel}")
        continue
    if live_f.exists():
        bak = BACKUP / stamp / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live_f, bak)
    live_f.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snap_f, live_f)
    print(f"[merged] {rel}  snap={snap_f.stat().st_size}B")

print("Done.")
