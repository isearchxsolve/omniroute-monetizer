"""Safe rescue-merge of snapshot-newer files into live projects.

Discipline (AGENTS.md): backup byte-for-byte BEFORE touching live, one-command
restore path, merge ONLY files where snapshot is genuinely newer, skip junk.

Targets (zero-risk / high-value):
  - voice_agent_avatar  (5 files, live has 0 newer)
  - ai_video_monetizer  (7 files, live has 0 newer)
  - antigravity-kandover (5 engine patches; preserves live selftest_quick_wrapper.py)
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

LASTHELP = Path(r"D:\god_ai\lasthelp\lasthelp")
BACKUP_ROOT = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue\pre_merge_backups")
MANIFEST = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue\rescue_manifest.json")

# project -> (live_root, [files to merge from snapshot])
MERGE_TARGETS = {
    "voice_agent_avatar": Path(r"D:\god_ai\voice_agent_avatar"),
    "ai_video_monetizer": Path(r"D:\god_ai\ai_video_monetizer"),
    "antigravity-kandover": Path(r"D:\dev\antigravity-kandover"),
}

manifest = json.load(open(MANIFEST))
direction = manifest["direction"]
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
merge_log = []

for proj, live_root in MERGE_TARGETS.items():
    snap_root = LASTHELP / proj
    snap_newer = direction.get(proj, {}).get("snapshot_newer", [])
    if not snap_newer:
        print(f"[skip] {proj}: no snapshot-newer files")
        continue

    print(f"\n=== {proj} ===")
    # 1) Backup only the specific live files we are about to overwrite
    for entry in snap_newer:
        rel = entry["file"]
        live_f = live_root / rel
        snap_f = snap_root / rel
        if not snap_f.exists():
            print(f"  [missing-snap] {rel}")
            continue
        # Backup existing live version (if any) before overwrite
        if live_f.exists():
            bak = BACKUP_ROOT / proj / stamp / rel
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(live_f, bak)
        # Merge: copy snapshot version into live
        live_f.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(snap_f, live_f)
        merge_log.append({
            "project": proj, "file": rel,
            "snap_size": entry["snap_size"], "live_size_before": entry["live_size"],
            "action": "overwritten" if live_f.exists() else "created",
        })
        print(f"  [merged] {rel}  ({entry['snap_size']}B)")

out = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue\merge_log.json")
existing = []
if out.exists():
    existing = json.load(open(out))
existing.extend(merge_log)
out.write_text(json.dumps(existing, indent=2), encoding="utf-8")
print(f"\nMerged {len(merge_log)} files. Backups -> {BACKUP_ROOT}")
print(f"Merge log -> {out}")
