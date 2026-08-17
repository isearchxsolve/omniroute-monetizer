#!/usr/bin/env python3
"""Preview which scan entries the deep probe would select as candidates."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
scan = json.loads((ROOT / "state" / "provider_upstream_scan.json").read_text(encoding="utf-8"))["results"]

print("=== status 200 entries ===")
for slug, r in sorted(scan.items()):
    if r.get("status") == 200:
        snip = (r.get("body_snippet") or "").lstrip()[:60]
        print(f"  {slug:20s} probed={r.get('probed')!s:60s} json={snip.lstrip().startswith(('{','['))} {snip!r}")

print("\n=== freeaiapikey body ===")
print(repr(scan.get("freeaiapikey", {}).get("body_snippet")))
