#!/usr/bin/env python3
"""
Deactivate invalid or failed connections to keep the routing mesh 100% healthy.
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

pw = resolve_password()
api = OmniRouteAPI(password=pw)
if not api.login():
    print("Login failed")
    sys.exit(1)

health_file = PROJECT_ROOT / "state" / "model_sync_health.json"
if not health_file.exists():
    print("No health file found.")
    sys.exit(1)

data = json.loads(health_file.read_text(encoding="utf-8"))
deactivated = 0
for item in data:
    if not item.get("test_valid"):
        cid = item.get("id")
        pname = item.get("provider")
        print(f"[+] Deactivating unhealthy connection {pname} (ID: {cid})...")
        payload = {
            "isActive": False
        }
        res = api.update_connection(cid, payload)
        if res.get("id") or "success" in str(res).lower() or res.get("isActive") is False:
            print(f"    Successfully deactivated {pname}.")
            deactivated += 1
        else:
            print(f"    Result: {res}")

print(f"[+] Deactivated {deactivated} unhealthy connections.")
