#!/usr/bin/env python3
"""List the 15 NEEDS_BROWSER providers with their baseUrls + authType."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
scan = json.loads((ROOT / "state" / "provider_upstream_scan.json").read_text(encoding="utf-8"))["results"]

nb = {k: v for k, v in scan.items() if v.get("verdict") == "NEEDS_BROWSER"}
print(f"{len(nb)} NEEDS_BROWSER providers\n")
for k in sorted(nb):
    v = nb[k]
    print(f"  {k:24s} auth={str(v.get('declared_authType')):8s} {v.get('baseUrl')}")
