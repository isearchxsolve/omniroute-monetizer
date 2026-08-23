"""Test agentrouter models through OmniRoute and direct upstream.
"""
from __future__ import annotations
import requests
import json

key = "sk-S3e9J5QlH4wt046tQPwDCbFfpYrAFx2cMNzkMDjLLBYgdYgb"

print("[*] Probing direct agentrouter upstream models...")
try:
    r = requests.get("https://api.agentrouter.org/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=8)
    print("Direct models status:", r.status_code)
    if r.status_code == 200:
        models = [m.get("id") for m in r.json().get("data", [])]
        print(f"Direct models ({len(models)}):", models[:10])
except Exception as e:
    print("Direct models error:", e)

# Test chat completions on OmniRoute
for m in ["agentrouter/auto", "agentrouter/gpt-4o", "agentrouter/claude-3-5-sonnet", "agentrouter/deepseek-v3"]:
    try:
        cr = requests.post(
            "http://localhost:20128/v1/chat/completions",
            json={"model": m, "messages": [{"role": "user", "content": "hi"}], "stream": False, "max_tokens": 10},
            timeout=10
        )
        print(f"OmniRoute {m:35} -> HTTP {cr.status_code} | {cr.text[:100]}")
    except Exception as e:
        print(f"OmniRoute {m:35} -> Error: {e}")
