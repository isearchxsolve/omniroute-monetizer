#!/usr/bin/env python3
"""Read-only comparison of configured combos against OmniRoute's live model catalog."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

DEFAULT_OUTPUT = ROOT / "state" / "omniroute_combo_catalog_audit.json"


def extract_rows(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get(key, [])
    return payload if isinstance(payload, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:20128")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    api = OmniRouteAPI(base_url=args.base, password=resolve_password())
    if not api.login():
        print("management login failed")
        return 1
    session = api.session
    try:
        combos_response = session.get(f"{api.api}/combos", timeout=args.timeout)
        models_response = session.get(f"{api.v1}/models", timeout=args.timeout)
    except Exception as exc:
        print(f"read failed: {type(exc).__name__}")
        return 1
    if not combos_response.ok or not models_response.ok:
        print(f"read failed: combos={combos_response.status_code} models={models_response.status_code}")
        return 1

    combos = extract_rows(combos_response.json(), "combos")
    models = extract_rows(models_response.json(), "data")
    live_ids = {str(item.get("id")) for item in models if item.get("id")}
    result_combos = []
    for combo in combos:
        configured = [str(item.get("model")) for item in (combo.get("models") or []) if item.get("model")]
        missing = [model for model in configured if model not in live_ids]
        result_combos.append({
            "id": combo.get("id"),
            "name": combo.get("name"),
            "modelCount": len(configured),
            "missingCount": len(missing),
            "missingModels": missing,
            "head": configured[0] if configured else None,
        })
    report = {
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "base": args.base.rstrip("/"),
        "readOnly": True,
        "comboCount": len(result_combos),
        "catalogModelCount": len(live_ids),
        "combosWithMissingModels": sum(1 for item in result_combos if item["missingCount"]),
        "combos": result_combos,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **{k: report[k] for k in ("comboCount", "catalogModelCount", "combosWithMissingModels")}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
