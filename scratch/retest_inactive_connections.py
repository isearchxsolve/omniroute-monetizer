#!/usr/bin/env python3
"""Re-test the 15 CONFIGURED_INACTIVE connections via POST /api/providers/{id}/test.
Reports which are actually alive upstream. Never prints secrets.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI

INACTIVE_IDS = [
    ("agy", "a4809bf3"),
    ("ainative", "811ba58f"),
    ("antigravity", "b727fc55"),
    ("cline", "c8a7f56f"),
    ("codex", "db2f61d1"),
    ("deepseek", "0b2d6fb0"),
    ("friendliai", "5c308db7"),
    ("grok-cli", "414a9dff"),
    ("huggingface", "983495e6"),
    ("lmarena", "a0e46e4e"),
    ("openai", "44010c8f"),
    ("qoder", "e217f911"),
    ("trae", "ad3b1ec6"),
    ("windsurf", "179e4825"),
    ("xai-oauth", "a2eced8e"),
]


def main() -> int:
    api = OmniRouteAPI()
    if not api.login():
        return 1
    conns = api.get_connections()
    by_prefix = {c["id"][:8]: c for c in conns}

    alive = []
    for slug, prefix in INACTIVE_IDS:
        c = by_prefix.get(prefix)
        if not c:
            print(f"  {slug:14} MISSING from connections")
            continue
        cid = c["id"]
        t0 = time.time()
        try:
            res = api.test_connection(cid)
        except Exception as e:
            print(f"  {slug:14} ERROR {str(e)[:60]}")
            continue
        dt = int((time.time() - t0) * 1000)
        result = res.get("result", {}) or {}
        valid = bool(result.get("valid"))
        diag = result.get("diagnosis", "")
        if isinstance(diag, dict):
            diag = diag.get("type", "")
        print(f"  {slug:14} valid={valid!s:5} {dt:5}ms diag={str(diag)[:50]}")
        if valid:
            alive.append((slug, cid))

    print(f"\nALIVE: {len(alive)} / {len(INACTIVE_IDS)}")
    for slug, cid in alive:
        print(f"  {slug}: {cid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
