"""Wire the Session Pool Shim into OmniRoute.

This script creates or updates an `openai` provider connection in OmniRoute
pointing to the local session_pool_shim running on port 8190.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI, log

def run():
    api = OmniRouteAPI()
    if not api.login():
        log("Management login failed; aborting", "err")
        sys.exit(1)

    r_existing = api.session.get(f"{api.api}/provider-nodes")
    existing_nodes = r_existing.json().get("nodes", []) if r_existing.status_code == 200 else []
    existing = next((n for n in existing_nodes if n.get("prefix") == "session-pool"), None)
    
    payload = {
        "name": "Session Pool Shim",
        "prefix": "session-pool",
        "apiType": "chat",
        "baseUrl": "http://127.0.0.1:8190/v1",
        "type": "openai-compatible"
    }

    if existing:
        nid = existing["id"]
        log(f"Session Pool node already exists (id={nid}); refreshing via PUT", "info")
        res = api.session.put(f"{api.api}/provider-nodes/{nid}", json=payload)
        log(f"PUT -> HTTP {res.status_code}", "ok")
    else:
        log("No Session Pool node yet; creating one via POST", "info")
        res = api.session.post(f"{api.api}/provider-nodes", json=payload)
        log(f"POST -> HTTP {res.status_code}", "ok")

    print("\nVerifying connection presence:")
    r_existing = api.session.get(f"{api.api}/provider-nodes")
    nodes = r_existing.json().get("nodes", []) if r_existing.status_code == 200 else []
    sp_node = next((n for n in nodes if n.get("prefix") == "session-pool"), None)
    if not sp_node:
        print("Error: Node not found after creation attempt.")
        sys.exit(2)
        
    node_id = sp_node.get("id")
    provider_id = node_id
    print(f"Node created. Virtual provider ID: {provider_id}")
    
    # 2. Create connection for the node
    conns = api.get_connections()
    existing_conn = next((c for c in conns if str(c.get("provider")) == provider_id), None)
    
    conn_payload = {
        "provider": provider_id,
        "name": "Session Pool Credentials",
        "apiKey": "sk-session-pool",
        "authType": "apikey",
        "isActive": True,
        "priority": 1,
    }
    
    if existing_conn:
        cid = existing_conn["id"]
        log(f"Session Pool connection already exists (id={cid}); refreshing via PUT", "info")
        res = api.update_connection(cid, conn_payload)
        log(f"PUT connection -> HTTP {res.get('http_status')}", "ok")
    else:
        log("No Session Pool connection yet; creating one via POST", "info")
        res = api.create_connection(conn_payload)
        log(f"POST connection -> HTTP {res.get('http_status')}", "ok")
        
    print("Success!")

if __name__ == "__main__":
    run()
