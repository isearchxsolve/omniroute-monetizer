#!/usr/bin/env python3
"""Combo health audit: list all combos, their model entries, and verify the
performance invariant (fast tool-call-capable models as priority #1)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI

FAST_MODELS = {
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-nano-12b-v2-vl",
}

TARGET_COMBOS = {
    "frontier", "auto/best-coding", "auto/best-reasoning", "auto/best-chat",
    "auto/pro-coding", "auto/pro-reasoning", "auto/pro-chat",
    "fusion-coder", "kimi-coding",
}


def main() -> int:
    api = OmniRouteAPI()
    if not api.login():
        return 1
    r = api.session.get(f"{api.api}/combos", timeout=30)
    combos = r.json()
    items = combos.get("combos", combos if isinstance(combos, list) else [])
    print(f"total combos: {len(items)}")
    issues = []
    for c in items:
        cid = c.get("id", "?")
        models = c.get("models", [])
        name = c.get("name") or cid
        heads = [m.get("model") for m in models if (m.get("priority", 99) == 0)]
        if not heads and models:
            heads = [models[0].get("model")]
        flag = ""
        if name in TARGET_COMBOS or cid in TARGET_COMBOS:
            if not any(h in FAST_MODELS for h in heads if h):
                flag = "  <-- no fast head at priority 0"
                issues.append((name, heads))
        print(f"  {name:28} models={len(models):2} heads={heads}{flag}")
    print(f"\ncombos missing fast priority-0 head: {len(issues)}")
    for name, heads in issues:
        print(f"  - {name}: heads={heads}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
