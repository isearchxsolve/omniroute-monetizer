#!/usr/bin/env python3
"""Check existing OmniRoute connections for chatgpt-web / gemini-web (read-only)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "automation")))
sys.stdout.reconfigure(encoding="utf-8")

from omniroute_api import OmniRouteAPI, mask_token

api = OmniRouteAPI()
if not api.login():
    print("LOGIN FAILED")
    raise SystemExit(1)

conns = api.get_connections()
print(f"total connections: {len(conns)}\n")
for c in conns:
    prov = c.get("provider")
    if prov in ("chatgpt-web", "gemini-web", "chatgpt", "gemini", "openai", "google"):
        key = c.get("apiKey") or ""
        print(f"  id={c.get('id')} provider={prov} authType={c.get('authType')} "
              f"isActive={c.get('isActive')} testStatus={c.get('testStatus')} "
              f"apiKey={mask_token(key)}")
