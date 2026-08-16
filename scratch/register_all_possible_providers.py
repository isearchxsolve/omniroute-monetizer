#!/usr/bin/env python3
"""
Test every known provider slug against POST /api/providers to register all valid providers.
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

# Load catalog
with open(PROJECT_ROOT / "state" / "all_295_providers_catalog.json", "r", encoding="utf-8") as f:
    data = json.load(f)

providers_dict = data.get("providers", {})
existing = api.get_connections()
existing_slugs = {c.get("provider") for c in existing}

print(f"[+] Total catalog items: {len(providers_dict)}")
print(f"[+] Already registered provider slugs: {len(existing_slugs)}")

success_count = 0

for slug, item in providers_dict.items():
    if slug in existing_slugs:
        continue
    
    clean_name = item.get("name", slug).split("\n")[0].strip()
    
    # Try different authTypes
    for auth_type in ["apikey", "none", "oauth"]:
        payload = {
            "provider": slug,
            "name": clean_name or slug,
            "authType": auth_type,
            "isActive": True,
            "apiKey": "auto-provisioned" if auth_type == "apikey" else ""
        }
        try:
            r = api.session.post(f"{api.api}/providers", json=payload, timeout=5)
            if r.status_code in (200, 201):
                print(f"[+] Successfully registered provider: {slug} (authType={auth_type})")
                success_count += 1
                existing_slugs.add(slug)
                break
        except Exception:
            pass

print(f"\n[+] Total additional providers registered into DB: {success_count}")
print(f"[+] Total unique providers in DB now: {len(existing_slugs)}")
