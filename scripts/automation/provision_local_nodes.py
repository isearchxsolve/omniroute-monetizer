#!/usr/bin/env python3
"""
Provision local & open engine Provider Nodes in OmniRoute via POST /api/provider-nodes.
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
    print("Login failed")
    sys.exit(1)

# List of open and local engines
LOCAL_ENGINES = [
    {"name": "Ollama Local Engine", "prefix": "ollama", "baseUrl": "http://127.0.0.1:11434/v1"},
    {"name": "LM Studio Engine", "prefix": "lmstudio", "baseUrl": "http://127.0.0.1:1234/v1"},
    {"name": "vLLM High-Throughput Engine", "prefix": "vllm", "baseUrl": "http://127.0.0.1:8000/v1"},
    {"name": "LocalAI Local Engine", "prefix": "localai", "baseUrl": "http://127.0.0.1:8080/v1"},
    {"name": "Jan AI Desktop Engine", "prefix": "jan", "baseUrl": "http://127.0.0.1:1337/v1"},
    {"name": "Text Generation WebUI", "prefix": "oobabooga", "baseUrl": "http://127.0.0.1:5000/v1"},
    {"name": "KoboldCPP Engine", "prefix": "koboldcpp", "baseUrl": "http://127.0.0.1:5001/v1"},
    {"name": "Tabby Code Server", "prefix": "tabby", "baseUrl": "http://127.0.0.1:8088/v1"},
    {"name": "FastChat Serving Engine", "prefix": "fastchat", "baseUrl": "http://127.0.0.1:21002/v1"}
]

# Get existing nodes
r_existing = api.session.get(f"{api.api}/provider-nodes")
existing_nodes = r_existing.json().get("nodes", []) if r_existing.status_code == 200 else []
existing_prefixes = {n.get("prefix") for n in existing_nodes}

print(f"[+] Existing provider nodes: {len(existing_nodes)} ({existing_prefixes})")

created = 0
for eng in LOCAL_ENGINES:
    if eng["prefix"] in existing_prefixes:
        print(f"[*] Node '{eng['prefix']}' already configured.")
        continue
    payload = {
        "name": eng["name"],
        "prefix": eng["prefix"],
        "apiType": "chat",
        "baseUrl": eng["baseUrl"],
        "type": "openai-compatible"
    }
    r = api.session.post(f"{api.api}/provider-nodes", json=payload)
    if r.status_code == 201:
        print(f"[+] Successfully created provider node '{eng['prefix']}' ({eng['name']})")
        created += 1
    else:
        print(f"[-] Failed to create node '{eng['prefix']}': {r.status_code} - {r.text}")

print(f"[+] Finished. Created {created} new provider nodes.")
