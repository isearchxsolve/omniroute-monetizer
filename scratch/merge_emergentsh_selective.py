"""emergentsh selective merge — evidence-based per-file decisions.

MERGE (6):
  - backend/app/api/projects.py          : adds project-ownership 404 checks (security fix)
  - backend/app/services/nim_client.py   : fixes leading-slash bug dropping /v1 base path
  - backend/code_generation.py           : live file is CORRUPTED (repeated import garbage);
                                           snapshot is a clean adapter -> agent_pipeline (exists in live)
  - backend/tests/test_nim_client.py     : proper async tests matching the /v1 fix
  - src/ui/widgets/auth/auth_dialog.py   : redacts placeholder key (T11 compliance)
  - neon_architect.py                    : removes duplicated _refill()/_prune() calls

SKIP (3):
  - backend/requirements.txt             : 0 diff lines (identical content)
  - tests/test_nim_client.py             : snapshot patches _request_json which does NOT exist
                                           in live's sync NIMClient (has _post/_get) -> would break
  - neon_architect_v4_7_mobile_env.py    : LIVE is genuinely newer (Aug 5, +80KB: RC-2 corruption
                                           detection, load-spreading rotate fix, longer timeouts)

Backups before every overwrite.
"""
import shutil
from datetime import datetime
from pathlib import Path

SNAP = Path(r"D:\god_ai\lasthelp\lasthelp\emergentsh")
LIVE = Path(r"C:\god_ai\emergentsh")
BACKUP = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue\pre_merge_backups\emergentsh")

MERGE = [
    "backend/app/api/projects.py",
    "backend/app/services/nim_client.py",
    "backend/code_generation.py",
    "backend/tests/test_nim_client.py",
    "src/ui/widgets/auth/auth_dialog.py",
    "neon_architect.py",
]
SKIP = [
    ("backend/requirements.txt", "identical content (0 diff lines)"),
    ("tests/test_nim_client.py", "patches _request_json absent from live sync NIMClient"),
    ("neon_architect_v4_7_mobile_env.py", "live genuinely newer (RC-2 + rotate fix)"),
]

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log = []

for rel in MERGE:
    s, l = SNAP / rel, LIVE / rel
    if not s.exists():
        print(f"[missing-snap] {rel}")
        continue
    if l.exists():
        bak = BACKUP / stamp / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(l, bak)
    l.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(s, l)
    log.append({"file": rel, "action": "merged", "size": s.stat().st_size})
    print(f"[merged] {rel}  ({s.stat().st_size}B)")

for rel, reason in SKIP:
    log.append({"file": rel, "action": "skipped", "reason": reason})
    print(f"[skipped] {rel}  -- {reason}")

import json
out = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue\merge_log.json")
existing = json.load(open(out)) if out.exists() else []
existing.append({"project": "emergentsh", "stamp": stamp, "entries": log})
out.write_text(json.dumps(existing, indent=2), encoding="utf-8")
print(f"\nDone. Merge log -> {out}")
