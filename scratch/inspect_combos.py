#!/usr/bin/env python3
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

pw = resolve_password()
api = OmniRouteAPI(password=pw)
api.login()

r = api.session.get(f"{api.api}/combos")
print("Response keys/type:", type(r.json()))
data = r.json()
combos_list = data if isinstance(data, list) else data.get("combos", data.get("data", []))
print(f"[+] Total combos: {len(combos_list)}")
for c in combos_list:
    if isinstance(c, dict):
        print(f"  - {c.get('name')} (ID: {c.get('id')}): {len(c.get('models', []))} models")
        for m in c.get('models', [])[:3]:
            print(f"      * {m.get('model')} (provider: {m.get('providerId')})")
    else:
        print("  - Item:", c)
