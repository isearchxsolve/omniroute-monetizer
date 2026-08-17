"""Content-hash divergence audit: live fleet projects vs lasthelp snapshots.

For each project pair, reports:
  - ONLY_LASTHELP : files present only in the lasthelp snapshot (rescue candidates)
  - ONLY_LIVE     : files present only in the live copy
  - DIFFERS       : files in both with different SHA-256 (real divergence)

Noise dirs (node_modules, .git, caches, venvs, build outputs) are excluded.
Output: scratch/lasthelp_divergence_report.json + console summary.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

LASTHELP = Path(r"D:\god_ai\lasthelp\lasthelp")

PAIRS = {
    "antigravity-kandover": Path(r"D:\dev\antigravity-kandover"),
    "ases_v3_1": Path(r"C:\god_ai\ases_v3_1"),
    "crypto-trader-v1_1": Path(r"C:\god_ai\crypto-trader-v1_1"),
    "neon_unified": Path(r"D:\neon_unified"),
    "emergentsh": Path(r"C:\god_ai\emergentsh"),
    "voice_agent_avatar": Path(r"D:\god_ai\voice_agent_avatar"),
    "ai_video_monetizer": Path(r"D:\god_ai\ai_video_monetizer"),
}

EXCLUDE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", ".audit-venv",
    "dist", "build", ".next", ".nuxt", ".pytest_cache", ".hypothesis",
    ".pnpm-store", "coverage", ".dart_tool", ".idea", ".vscode",
    ".gradle", ".flutter-plugins", ".flutter-plugins-dependencies",
    "target", ".mypy_cache", ".ruff_cache", ".tox", "eggs", ".eggs",
    "site-packages", ".cache", ".turbo", ".parcel-cache",
}

# Skip very large binary/media files from hashing but still list them
MAX_HASH_SIZE = 50 * 1024 * 1024  # 50 MB


def walk_files(root: Path):
    """Yield (relpath, abspath) for all non-excluded files under root."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            ap = Path(dirpath) / fn
            rel = ap.relative_to(root).as_posix()
            yield rel, ap


def sha256(path: Path):
    try:
        if path.stat().st_size > MAX_HASH_SIZE:
            return f"TOO_LARGE:{path.stat().st_size}"
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as e:
        return f"ERROR:{e}"


def audit_project(name: str, live_root: Path):
    snap_root = LASTHELP / name
    result = {
        "live": str(live_root),
        "snapshot": str(snap_root),
        "live_exists": live_root.exists(),
        "snapshot_exists": snap_root.exists(),
        "only_lasthelp": [],
        "only_live": [],
        "differs": [],
        "identical_count": 0,
    }
    if not result["live_exists"] or not result["snapshot_exists"]:
        return result

    live_files = dict(walk_files(live_root))
    snap_files = dict(walk_files(snap_root))

    live_set = set(live_files)
    snap_set = set(snap_files)

    result["only_lasthelp"] = sorted(snap_set - live_set)
    result["only_live_count"] = len(live_set - snap_set)

    common = live_set & snap_set
    for rel in sorted(common):
        lh = sha256(live_files[rel])
        sh = sha256(snap_files[rel])
        if lh == sh:
            result["identical_count"] += 1
        else:
            result["differs"].append({
                "file": rel,
                "live_size": live_files[rel].stat().st_size,
                "snap_size": snap_files[rel].stat().st_size,
                "snap_mtime": snap_files[rel].stat().st_mtime,
            })
    return result


def main():
    report = {}
    for name, live in PAIRS.items():
        print(f"\n=== {name} ===", flush=True)
        r = audit_project(name, live)
        report[name] = r
        if not (r["live_exists"] and r["snapshot_exists"]):
            print(f"  SKIPPED (live={r['live_exists']}, snapshot={r['snapshot_exists']})")
            continue
        print(f"  identical: {r['identical_count']}")
        print(f"  DIFFERS (content): {len(r['differs'])}")
        print(f"  ONLY_LASTHELP: {len(r['only_lasthelp'])}")
        print(f"  ONLY_LIVE: {r['only_live_count']}")
        # Show top 10 most recent differing files (likely the real patches)
        top = sorted(r["differs"], key=lambda d: -d["snap_mtime"])[:10]
        for d in top:
            print(f"    ~ {d['file']} (snap {d['snap_size']}B vs live {d['live_size']}B)")

    out = Path(__file__).parent / "lasthelp_divergence_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nFull report written to {out}")


if __name__ == "__main__":
    sys.exit(main())
