#!/usr/bin/env python3
"""Create a native-API snapshot of OmniRoute combo definitions before a combo update."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:20128")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "state" / "combo_backups")
    args = parser.parse_args()
    api = OmniRouteAPI(base_url=args.base, password=resolve_password())
    if not api.login():
        print("management login failed")
        return 1
    try:
        combos = api.get_combos()
    except Exception as exc:
        print(f"combo backup read failed: {type(exc).__name__}")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir / f"combos_{stamp}.json"
    output.write_text(json.dumps({"createdAt": dt.datetime.now(dt.timezone.utc).isoformat(), "combos": combos}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "comboCount": len(combos)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
