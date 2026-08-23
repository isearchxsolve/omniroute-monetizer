"""Query and summarize latest healthy providers and models from OmniRoute.
"""
from __future__ import annotations
import sys
import json
import pathlib
import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI

sys.stdout.reconfigure(encoding="utf-8")

def audit_healthy():
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        print("[-] Could not login to OmniRoute management API")
        return
        
    conns = api.get_connections()
    active_conns = [c for c in conns if c.get("isActive")]
    print(f"Total connections: {len(conns)} | Active connections: {len(active_conns)}")
    
    # Provider summary
    by_provider = {}
    for c in active_conns:
        p = c.get("provider", "unknown")
        by_provider.setdefault(p, []).append(c)
        
    print("\n--- ACTIVE PROVIDERS & AUTH TYPES ---")
    for p, items in sorted(by_provider.items()):
        auth_types = {item.get("authType") for item in items}
        print(f"  - {p:24} (connections: {len(items)}, auth: {', '.join(auth_types)})")
        
    # Check combos
    print("\n--- COMBOS & POWER CASCADES ---")
    combos = api.get_combos()
    for cb in combos:
        cid = cb.get("id")
        name = cb.get("name", cid)
        models = cb.get("models", [])
        m_list = [f"{m.get('providerId')}/{m.get('model')}" if isinstance(m, dict) else str(m) for m in models]
        print(f"  • {name} ({len(models)} models in cascade):")
        for m in m_list[:4]:
            print(f"      -> {m}")
        if len(m_list) > 4:
            print(f"      ... and {len(m_list) - 4} more fallback models")

if __name__ == "__main__":
    audit_healthy()
