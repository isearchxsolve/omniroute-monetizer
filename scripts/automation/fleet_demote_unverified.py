#!/usr/bin/env python3
"""Disable only currently-active providers disproven by a real fleet inference audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

INFERENCE = PROJECT_ROOT / "state" / "fleet_inference_repair.json"
OUTPUT = PROJECT_ROOT / "state" / "fleet_demotions.json"


def main() -> int:
    results = json.loads(INFERENCE.read_text(encoding="utf-8")).get("results", [])
    failed = {
        item["label"].split(":", 1)[1]
        for item in results
        if item.get("label", "").startswith("direct:") and not item.get("valid")
    }
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("ERROR management login failed")
        return 1
    changes = []
    for conn in api.get_connections():
        if conn.get("provider") not in failed or not conn.get("isActive"):
            continue
        result = api.update_connection(conn["id"], {"isActive": False})
        changes.append({"provider": conn.get("provider"), "id": conn.get("id"), "httpStatus": result.get("http_status")})
    OUTPUT.write_text(json.dumps({"failedInferenceProviders": sorted(failed), "changes": changes}, indent=2), encoding="utf-8")
    print(f"providers={len(failed)} disabled={sum(1 for item in changes if item['httpStatus'] == 200)} output={OUTPUT}")
    return 0 if all(item["httpStatus"] == 200 for item in changes) else 2


if __name__ == "__main__":
    raise SystemExit(main())
