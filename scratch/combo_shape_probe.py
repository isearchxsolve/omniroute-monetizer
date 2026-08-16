#!/usr/bin/env python3
"""Inspect raw combo list + detail response shapes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI


def main() -> int:
    api = OmniRouteAPI()
    if not api.login():
        return 1
    r = api.session.get(f"{api.api}/combos", timeout=30)
    combos = r.json()
    items = combos.get("combos", combos if isinstance(combos, list) else [])
    print("list item keys:", sorted(items[0].keys()) if items else "EMPTY")
    print("first item:", json.dumps(items[0], indent=1)[:600] if items else "")
    # try detail endpoint
    cid = items[0]["id"]
    r2 = api.session.get(f"{api.api}/combos/{cid}", timeout=30)
    print("\ndetail status:", r2.status_code)
    d = r2.json()
    print("detail keys:", sorted(d.keys()))
    data = d.get("data") or {}
    print("data.name:", data.get("name"), "| models:", len(data.get("models", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
