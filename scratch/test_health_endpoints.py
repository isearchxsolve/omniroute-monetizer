#!/usr/bin/env python3
"""
Test health-matrix and health-autopilot endpoints in OmniRoute.
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

pw = resolve_password()
api = OmniRouteAPI(password=pw)
if not api.login():
    print("[-] Login failed.")
    sys.exit(1)

# 1. Health matrix
try:
    r_mat = api.session.get(f"{api.api}/providers/health-matrix", timeout=10)
    print(f"GET /api/providers/health-matrix: HTTP {r_mat.status_code}")
    if r_mat.status_code == 200:
        print("Response (first 300 chars):", r_mat.text[:300])
except Exception as e:
    print(f"GET /api/providers/health-matrix error: {e}")

# 2. Health autopilot
try:
    r_auto = api.session.post(f"{api.api}/providers/health-autopilot", json={}, timeout=10)
    print(f"POST /api/providers/health-autopilot: HTTP {r_auto.status_code}")
    if r_auto.status_code == 200:
        print("Response:", r_auto.text[:300])
except Exception as e:
    print(f"POST /api/providers/health-autopilot error: {e}")
