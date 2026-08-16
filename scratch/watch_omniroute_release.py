"""OmniRoute v3.8.50 release watcher.
Polls npm dist-tags for the 'omniroute' package and alerts when a version
newer than 3.8.49 (i.e. the shipped blocker-#3 SWR fix) is published.

Usage:
  one-shot:   python watch_omniroute_release.py
  continuous: python watch_omniroute_release.py --loop [--interval 3600]

Writes state to state/release_watch.json and prints a loud ALERT line when
the target version appears. T11-safe: no secrets.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
STATE_FILE = os.path.join(STATE_DIR, "release_watch.json")
BASELINE = "3.8.49"  # last published version; blocker #3 fix lands in 3.8.50


def parse_ver(v):
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except Exception:
        return (0, 0, 0)


NODE_DIR = r"C:\Users\Admin\AppData\Local\hermes\node"
NPM_CLI = os.path.join(NODE_DIR, "node_modules", "npm", "bin", "npm-cli.js")


def query_npm():
    """Return (dist_tags_dict, latest_version_str) or (None, error)."""
    cmds = []
    # Strategy 1: node.exe + npm-cli.js (most reliable, no shell needed)
    if os.path.exists(NPM_CLI) and os.path.exists(os.path.join(NODE_DIR, "node.exe")):
        cmds.append([os.path.join(NODE_DIR, "node.exe"), NPM_CLI,
                     "view", "omniroute", "dist-tags", "--json"])
    # Strategy 2: cmd /c npm (resolves npm.cmd via PATH)
    cmds.append(["cmd", "/c", "npm", "view", "omniroute", "dist-tags", "--json"])
    last_err = "no npm strategy available"
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if out.returncode != 0:
                last_err = (out.stderr or out.stdout).strip()[:300]
                continue
            tags = json.loads(out.stdout)
            if isinstance(tags, list):  # npm wraps single-package output in an array
                tags = tags[0] if tags else {}
            if not isinstance(tags, dict):
                last_err = f"unexpected dist-tags shape: {type(tags).__name__}"
                continue
            return tags, tags.get("latest", "")
        except Exception as e:
            last_err = str(e)[:300]
    return None, last_err


def check_once():
    now = datetime.now(timezone.utc).isoformat()
    tags, latest = query_npm()
    rec = {"checked_at_utc": now, "dist_tags": tags, "latest": latest,
           "newer_than_baseline": False, "error": None}
    if tags is None:
        rec["error"] = latest
        print(f"[watch] {now} ERROR querying npm: {latest}")
    else:
        newer = [v for v in tags.values() if parse_ver(v) > parse_ver(BASELINE)]
        rec["newer_than_baseline"] = bool(newer)
        if newer:
            print("=" * 70)
            print(f"[watch] *** ALERT: OmniRoute newer than {BASELINE} is PUBLISHED! ***")
            print(f"[watch] dist-tags: {json.dumps(tags)}")
            print("[watch] The blocker #3 SWR fix (PR #8728/#8987/#9199) is now installable:")
            print("[watch]   npm install -g omniroute@latest   (then NSSM service bounce)")
            print("=" * 70)
        else:
            print(f"[watch] {now} latest={latest or '?'} — still no release newer than {BASELINE}.")
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)
    return rec


def main():
    loop = "--loop" in sys.argv
    interval = 3600
    if "--interval" in sys.argv:
        interval = int(sys.argv[sys.argv.index("--interval") + 1])
    if not loop:
        check_once()
        return
    print(f"[watch] continuous mode, interval={interval}s, Ctrl+C to stop")
    while True:
        rec = check_once()
        if rec.get("newer_than_baseline"):
            print("[watch] target published — exiting watcher.")
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
