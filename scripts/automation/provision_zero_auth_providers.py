#!/usr/bin/env python3
"""
Provision all built-in Zero-Auth and Public Providers into OmniRoute via POST /api/providers.
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

# List of zero-auth providers recognized by OmniRoute
NOAUTH_PROVIDERS = [
    {"provider": "duckduckgo-web", "name": "DuckDuckGo AI Chat (Zero-Auth)"},
    {"provider": "felo-web", "name": "Felo AI (Zero-Auth)"},
    {"provider": "theoldllm", "name": "The Old LLM (Zero-Auth)"},
    {"provider": "mimocode", "name": "MiMoCode (Zero-Auth)"},
    {"provider": "aihorde", "name": "AI Horde (Zero-Auth)"},
    {"provider": "chipotle", "name": "Chipotle AI (Zero-Auth)"},
    {"provider": "veoaifree-web", "name": "Veo AI Free (Zero-Auth)"}
]

# Get existing connections
existing = api.get_connections()
existing_providers = {c.get("provider") for c in existing}

print(f"[+] Currently existing providers in DB: {len(existing_providers)}")

created = 0
for p in NOAUTH_PROVIDERS:
    p_slug = p["provider"]
    if p_slug in existing_providers:
        print(f"[*] Provider '{p_slug}' already exists in DB.")
        continue
    
    payload = {
        "provider": p_slug,
        "name": p["name"],
        "authType": "none",
        "isActive": True,
        "apiKey": ""
    }
    
    try:
        r = api.session.post(f"{api.api}/providers", json=payload, timeout=10)
        print(f"[+] POST /api/providers for '{p_slug}': HTTP {r.status_code} -> {r.text[:200]}")
        if r.status_code in (200, 201):
            created += 1
            # Sync models for this new provider
            new_id = r.json().get("id")
            if new_id:
                r_sync = api.session.post(f"{api.api}/providers/{new_id}/sync-models", timeout=10)
                print(f"    Synced models: HTTP {r_sync.status_code}")
    except Exception as e:
        print(f"[-] Failed to create provider '{p_slug}': {e}")

print(f"\n[+] Total new Zero-Auth providers registered: {created}")
