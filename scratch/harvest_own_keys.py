"""Harvest the user's OWN API keys from OmniRoute connections (READ-ONLY).

Goal: point Copilot directly at upstream providers (nvidia, groq, cohere,
github, alibaba, cerebras, llm7, ...) using keys the user already owns,
bypassing the local router for maximum model availability.

Never prints full keys — only masked previews. Saves masked summary to
state/harvested_providers.json (keys included there ONLY for the installer,
redacted in any log).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
from oauth_keepalive import resolve_password

BASE = "http://127.0.0.1:20128"
OUT = Path(r"d:\omniroute-monetizer\state\harvested_providers.json")


def mask(k):
    if not k:
        return None
    k = str(k)
    return k[:8] + "..." + k[-4:] if len(k) > 14 else "***"


s = requests.Session()
for a in range(5):
    try:
        r = s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45)
        print(f"login: {r.status_code}")
        break
    except Exception as e:
        print(f"login retry {a+1}: {type(e).__name__}")
        time.sleep(10)

r = s.get(f"{BASE}/api/providers", timeout=90)
print(f"providers: {r.status_code}")
j = r.json()
conns = j.get("connections", j if isinstance(j, list) else [])
print(f"total connections: {len(conns)}")

sample = conns[0] if conns else {}
print("fields:", ", ".join(sample.keys()))

harvest = {}
for c in conns:
    prov = c.get("provider")
    key = c.get("apiKey")
    active = c.get("isActive")
    status = c.get("testStatus")
    if key and str(key) not in ("None", "") and active and status == "valid":
        harvest.setdefault(prov, []).append({
            "id": c.get("id"),
            "name": c.get("name"),
            "authType": c.get("authType"),
            "apiKey": key,
            "masked": mask(key),
            "testStatus": status,
        })

print(f"\nharvestable providers (active+valid+key visible): {len(harvest)}")
for prov, items in sorted(harvest.items()):
    for it in items:
        print(f"  {prov}: {it['authType']} key={it['masked']} name={it['name']}")

OUT.write_text(json.dumps(harvest, indent=2), encoding="utf-8")
print(f"\nSaved to {OUT} (contains keys - DO NOT commit/log)")
