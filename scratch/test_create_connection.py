#!/usr/bin/env python3
"""
Test POST /api/providers with name field.
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
    print("Login failed")
    sys.exit(1)

payload = {
    "provider": "ollama",
    "name": "Ollama Local Engine",
    "authType": "apikey",
    "apiKey": "ollama-local-key",
    "isActive": True,
    "providerSpecificData": {
        "baseUrl": "http://127.0.0.1:11434"
    }
}
r = api.session.post(f"{api.api}/providers", json=payload)
print(f"POST /api/providers -> HTTP {r.status_code}: {r.text}")

if r.status_code in [200, 201]:
    res = r.json()
    cid = res.get("id") or (res.get("connection", {}) if isinstance(res.get("connection"), dict) else {}).get("id")
    print(f"Created ID: {cid}")
    if cid:
        # test sync models
        r_sync = api.session.post(f"{api.api}/providers/{cid}/sync-models")
        print(f"sync-models: {r_sync.status_code} -> {r_sync.text[:200]}")
        # test connection
        r_test = api.session.post(f"{api.api}/providers/{cid}/test")
        print(f"test: {r_test.status_code} -> {r_test.text[:200]}")
