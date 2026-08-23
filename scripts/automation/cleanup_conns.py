"""Reconcile and cleanup temp connections in OmniRoute.
"""
from __future__ import annotations
import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI

sys.stdout.reconfigure(encoding="utf-8")

def cleanup():
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    conns = api.get_connections()
    print(f"[+] Total connections in OmniRoute: {len(conns)}")
    
    # Check for temporary test connections created in this session
    for c in conns:
        cid = c.get("id")
        provider = c.get("provider")
        name = c.get("name")
        created_at = c.get("createdAt")
        if provider in ("openadapter", "puter") and not c.get("isActive"):
            print(f"[-] Cleaning inactive connection: {cid} ({provider})")
            api.session.delete(f"{api.api}/providers/{cid}")

if __name__ == "__main__":
    cleanup()
