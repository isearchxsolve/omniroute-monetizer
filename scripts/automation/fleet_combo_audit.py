#!/usr/bin/env python3
"""Persist a credential-free management view of OmniRoute combos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402


def main() -> int:
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("ERROR management login failed")
        return 1
    combos = api.get_combos()
    safe = []
    for combo in combos:
        safe.append({
            "id": combo.get("id"),
            "name": combo.get("name"),
            "modelCount": len(combo.get("models") or []),
            "models": [item.get("model") for item in combo.get("models") or [] if item.get("model")],
        })
    output = PROJECT_ROOT / "state" / "fleet_combo_audit.json"
    output.write_text(json.dumps({"total": len(safe), "combos": safe}, indent=2), encoding="utf-8")
    print(f"total={len(safe)} output={output}")
    for combo in safe:
        print(f"{combo['name']} id={combo['id']} models={combo['modelCount']} head={(combo['models'] or ['-'])[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
