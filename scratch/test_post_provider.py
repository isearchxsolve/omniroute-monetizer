#!/usr/bin/env python3
"""
Test POST /api/providers to see connection creation schema and validation.
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

# Test 1: Empty POST to get validation errors
r = api.session.post(f"{api.api}/providers", json={})
print(f"Empty POST -> HTTP {r.status_code}: {r.text[:300]}")

# Test 2: Standard API key connection payload
payload = {
    "provider": "ollama",
    "authType": "apikey",
    "apiKey": "ollama-local",
    "isActive": True,
    "providerSpecificData": {
        "baseUrl": "http://127.0.0.1:11434"
    }
}
r2 = api.session.post(f"{api.api}/providers", json=payload)
print(f"Ollama POST -> HTTP {r2.status_code}: {r2.text[:300]}")

if r2.status_code == 200 or r2.status_code == 201:
    conn_data = r2.json()
    cid = conn_data.get("id") or conn_data.get("connection", {}).get("id")
    print(f"Created connection id: {cid}")
    if cid:
        # Test sync-models endpoint!
        r_sync = api.session.post(f"{api.api}/providers/{cid}/sync-models")
        print(f"Sync-models -> HTTP {r_sync.status_code}: {r_sync.text[:300]}")
        
        # Test test endpoint
        r_test = api.session.post(f"{api.api}/providers/{cid}/test")
        print(f"Test -> HTTP {r_test.status_code}: {r_test.text[:300]}")
