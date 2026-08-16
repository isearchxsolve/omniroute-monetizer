#!/usr/bin/env python3
"""
Inspect Windsurf and Trae connections in OmniRoute.
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI, redact, mask_token
from oauth_keepalive import resolve_password

pw = resolve_password()
api = OmniRouteAPI(password=pw)
if not api.login():
    print("Failed to login to OmniRoute API")
    sys.exit(1)

r = api.session.get(f"{api.api}/providers")
if r.status_code != 200:
    print(f"Failed to get providers: {r.status_code}")
    sys.exit(1)

data = r.json()
conns = data.get("connections", [])
print(f"Total connections: {len(conns)}")
for c in conns:
    p = c.get("provider", "")
    if any(x in p.lower() for x in ["windsurf", "trae", "codeium", "claude", "anthropic"]):
        print(f"\nProvider: {p} (id: {c.get('id')})")
        print(f"  authType: {c.get('authType')}")
        print(f"  isActive: {c.get('isActive')}")
        print(f"  testStatus: {c.get('testStatus')}")
        print(f"  apiKey: {mask_token(c.get('apiKey', ''))}")
        print(f"  providerSpecificData keys: {list((c.get('providerSpecificData') or {}).keys())}")
