"""Check live OmniRoute connection state: active by provider, gemini/groq detail."""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from automation.omniroute_api import OmniRouteAPI

client = OmniRouteAPI()
if not client.login():
    print("LOGIN FAILED")
    sys.exit(1)

conns = client.get_connections()
print(f"total connections: {len(conns)}")

by_provider = {}
for c in conns:
    prov = c.get("provider") or "?"
    by_provider.setdefault(prov, []).append(c)

active_providers = {}
for prov, cs in by_provider.items():
    live = [c for c in cs if c.get("isActive")]
    if live:
        active_providers[prov] = (len(cs), len(live))

print(f"\nproviders with >=1 ACTIVE connection: {len(active_providers)}")
for prov in sorted(active_providers):
    n, nlive = active_providers[prov]
    print(f"  {prov:28s} conns={n} active={nlive}")

print("\n--- gemini / groq / openrouter / nvidia / anthropic / github detail ---")
for prov in ("gemini", "groq", "openrouter", "nvidia", "anthropic", "github"):
    cs = by_provider.get(prov, [])
    if not cs:
        print(f"  {prov}: NO connections")
        continue
    for c in cs:
        safe = {k: c.get(k) for k in ("id", "provider", "isActive", "status", "testStatus", "label", "authType", "name")}
        key = c.get("apiKey")
        safe["apiKey_masked"] = (key[:8] + "..." + key[-4:]) if isinstance(key, str) and len(key) > 12 else None
        print(f"  {prov}: {json.dumps(safe)}")
