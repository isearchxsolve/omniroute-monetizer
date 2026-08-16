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

r = api.session.get(f"{api.api}/providers/health-matrix")
if r.status_code == 200:
    data = r.json()
    print("Summary:", json.dumps(data.get("summary"), indent=2))
    print(f"Found {len(data.get('providers', []))} providers in health matrix:")
    for p in data.get("providers", []):
        print(f"  - {p.get('provider')}: state={p.get('state')}, score={p.get('score')}, circuitBreaker={p.get('circuitBreaker')}")
