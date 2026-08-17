"""Rescue ONLY_LASTHELP files to staging + classify DIFFERS direction by mtime.

Stage 1 (safe): copy snapshot-only files to state/lasthelp_rescue/<project>/
Stage 2 (info): for content-differing files, compare mtimes to decide which
side is newer -> SNAPSHOT_NEWER (candidate to merge into live) vs LIVE_NEWER
(live wins, snapshot is stale).
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

LASTHELP = Path(r"D:\god_ai\lasthelp\lasthelp")
REPORT = Path(__file__).parent / "lasthelp_divergence_report.json"
STAGING = Path(r"d:\omniroute-monetizer\state\lasthelp_rescue")

# Junk patterns we do NOT rescue
JUNK_NAMES = {".coverage", "{", "=6.6.0", "server.log"}
JUNK_SUBSTR = (" - Copy",)

report = json.load(open(REPORT))
rescue_manifest = []

print("=" * 60)
print("STAGE 1: RESCUE snapshot-only files to staging")
print("=" * 60)

for proj, data in report.items():
    for rel in data.get("only_lasthelp", []):
        fname = Path(rel).name
        if fname in JUNK_NAMES or any(s in rel for s in JUNK_SUBSTR):
            print(f"  [skip-junk] {proj}/{rel}")
            continue
        src = LASTHELP / proj / rel
        dst = STAGING / proj / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst)
            size = src.stat().st_size
            rescue_manifest.append({"project": proj, "file": rel, "size": size})
            tag = " [SECRET-DO-NOT-PRINT]" if fname == ".env" else ""
            print(f"  [rescued] {proj}/{rel} ({size}B){tag}")
        except OSError as e:
            print(f"  [ERROR] {proj}/{rel}: {e}")

print(f"\nTotal rescued: {len(rescue_manifest)} files -> {STAGING}")

print("\n" + "=" * 60)
print("STAGE 2: DIFFERS direction by mtime")
print("=" * 60)

direction_summary = {}
for proj, data in report.items():
    live_root = Path(data["live"])
    snap_root = Path(data["snapshot"])
    snap_newer, live_newer, unclear = [], [], []
    for d in data.get("differs", []):
        rel = d["file"]
        # skip pure noise (logs, coverage html, heartbeats)
        low = rel.lower()
        if any(x in low for x in ("htmlcov/", "coverage.xml", ".heartbeat",
                                   "last_scan.json", "logs/", "server.log")):
            continue
        live_f = live_root / rel
        snap_f = snap_root / rel
        if not live_f.exists() or not snap_f.exists():
            unclear.append(rel)
            continue
        lm = live_f.stat().st_mtime
        sm = snap_f.stat().st_mtime
        entry = {
            "file": rel,
            "live_mtime": datetime.fromtimestamp(lm).isoformat(),
            "snap_mtime": datetime.fromtimestamp(sm).isoformat(),
            "live_size": d["live_size"],
            "snap_size": d["snap_size"],
        }
        if sm > lm:
            snap_newer.append(entry)
        elif lm > sm:
            live_newer.append(entry)
        else:
            unclear.append(rel)
    direction_summary[proj] = {
        "snapshot_newer": snap_newer,
        "live_newer": live_newer,
        "unclear": unclear,
    }
    print(f"\n=== {proj} ===")
    print(f"  SNAPSHOT_NEWER (merge candidates): {len(snap_newer)}")
    for e in snap_newer:
        print(f"    <- {e['file']}  snap={e['snap_mtime'][:16]} live={e['live_mtime'][:16]}")
    print(f"  LIVE_NEWER (live wins): {len(live_newer)}")
    for e in live_newer:
        print(f"    -> {e['file']}  live={e['live_mtime'][:16]} snap={e['snap_mtime'][:16]}")
    if unclear:
        print(f"  UNCLEAR: {len(unclear)}: {unclear[:5]}")

out = STAGING / "rescue_manifest.json"
out.write_text(json.dumps({
    "rescued": rescue_manifest,
    "direction": direction_summary,
}, indent=2), encoding="utf-8")
print(f"\nManifest + direction analysis -> {out}")
