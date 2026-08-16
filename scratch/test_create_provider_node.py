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

payload = {
    "name": "Ollama Local Engine",
    "prefix": "ollama",
    "apiType": "chat",
    "baseUrl": "http://127.0.0.1:11434/v1",
    "type": "openai-compatible"
}

r = api.session.post(f"{api.api}/provider-nodes", json=payload)
print("POST /api/provider-nodes:", r.status_code, r.text)

r2 = api.session.get(f"{api.api}/provider-nodes")
print("GET /api/provider-nodes:", r2.status_code, r2.text)
