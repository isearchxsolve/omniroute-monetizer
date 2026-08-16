#!/usr/bin/env python3
"""Inspect model structure in catalog."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()
models = api.list_models()

print(f"[*] Total models: {len(models)}\n")

# Show first 5 models with full structure
print("[*] First 5 models:")
for m in models[:5]:
    print(json.dumps(m, indent=2))
    print()

# Show models that look like real options (not combos)
real_models = [m for m in models if not m['id'].startswith('auto/')]
print(f"\n[*] Non-combo models: {len(real_models)}")
if real_models:
    print("\nFirst 10 real models:")
    for m in real_models[:10]:
        print(json.dumps(m, indent=2)[:300])
        print()

save_json('model_structure_sample.json', {
    'sample_combos': models[:5],
    'real_models_sample': real_models[:10] if real_models else [],
})
