#!/usr/bin/env python3
"""
Inspect the full 295 provider catalog in OmniRoute.
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "automation"))
from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

pw = resolve_password()
api = OmniRouteAPI(password=pw)
if not api.login():
    print("Failed to login to OmniRoute")
    sys.exit(1)

# Check all available endpoints related to providers
endpoints = [
    "/api/providers",
    "/api/providers/templates",
    "/api/providers/catalog",
    "/api/discovery",
    "/api/settings",
    "/v1/models"
]

for ep in endpoints:
    try:
        r = api.session.get(f"{api.base}{ep}", timeout=10)
        print(f"{ep} -> HTTP {r.status_code} (len={len(r.text)})")
        if r.status_code == 200:
            try:
                data = r.json()
                if isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())}")
                    for k in data.keys():
                        v = data[k]
                        if isinstance(v, list):
                            print(f"    {k}: list of {len(v)} items")
                        elif isinstance(v, dict):
                            print(f"    {k}: dict of {len(v)} keys")
                elif isinstance(data, list):
                    print(f"  List of {len(data)} items")
            except Exception:
                pass
    except Exception as e:
        print(f"{ep} -> Error: {e}")
