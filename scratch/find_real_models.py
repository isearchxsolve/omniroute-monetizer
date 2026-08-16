#!/usr/bin/env python3
"""Find REAL available models in OmniRoute catalog."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()
models = api.list_models()

# Group by provider
by_provider = {}
for m in models:
    prov = m.get('provider', 'unknown')
    if prov not in by_provider:
        by_provider[prov] = []
    by_provider[prov].append(m['id'])

print(f"[*] {len(models)} total models across {len(by_provider)} providers\n")

# Show providers with most models
for prov in sorted(by_provider.keys(), key=lambda p: len(by_provider[p]), reverse=True)[:15]:
    count = len(by_provider[prov])
    print(f"{prov}: {count} models")
    # Show first 3
    for mid in by_provider[prov][:3]:
        print(f"  {mid}")

# Check for specific providers that work
print("\n[*] Active providers (from earlier harvest):")
for prov in ['openrouter', 'nvidia', 'ainative', 'agy', 'opencode']:
    if prov in by_provider:
        print(f"\n{prov}: {len(by_provider[prov])} models")
        for mid in sorted(by_provider[prov])[:5]:
            print(f"  {mid}")

save_json('real_model_catalog.json', by_provider)
