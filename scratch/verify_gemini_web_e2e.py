#!/usr/bin/env python3
"""End-to-end verify the new gemini-web connection serves real inference via /v1.
Uses a valid standard chat payload (AGENTS.md rule 3). Redacted output."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "automation"))

import requests  # noqa: E402
from omniroute_api import OmniRouteAPI  # noqa: E402
from oauth_keepalive import resolve_password  # noqa: E402

api = OmniRouteAPI(password=resolve_password())
api.login()

# find gemini-web connection + its models
conns = api.get_connections()
gw = next((c for c in conns if c.get("provider") == "gemini-web"), None)
if not gw:
    print("[-] no gemini-web connection")
    raise SystemExit(1)
cid = gw["id"]
print(f"gemini-web conn {cid} isActive={gw.get('isActive')} testStatus={gw.get('testStatus')}")

# list models attributed to this provider
r = requests.get(f"{api.base}/v1/models", timeout=30)
models = r.json().get("data", []) if r.status_code == 200 else []
gw_models = [m.get("id") for m in models
             if (m.get("providerId") == cid or "gemini-web" in str(m.get("id", "")))]
print(f"total /v1 models={len(models)}; gemini-web-attributed={len(gw_models)}")
print(f"  sample: {gw_models[:8]}")

# pick a chat model and run a valid completion
target = None
for m in gw_models:
    if any(k in m.lower() for k in ("gemini", "flash", "pro")):
        target = m
        break
target = target or (gw_models[0] if gw_models else None)
if not target:
    print("[-] no gemini-web model to test")
    raise SystemExit(2)

print(f"\nprobing /v1/chat/completions with model={target}")
payload = {"model": target,
           "messages": [{"role": "user",
                         "content": "Reply with exactly one word: hello"}],
           "max_tokens": 32, "temperature": 0, "stream": False}
resp = requests.post(f"{api.base}/v1/chat/completions", json=payload, timeout=90)
print(f"  HTTP {resp.status_code}")
if resp.status_code == 200:
    j = resp.json()
    choice = (j.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content", "")
    print(f"  content={content[:80]!r}")
    print(f"  usage={j.get('usage')}")
    print("[+] GEMINI-WEB END-TO-END LIVE")
else:
    print(f"  body={resp.text[:300]}")
    print("[-] inference probe failed")
