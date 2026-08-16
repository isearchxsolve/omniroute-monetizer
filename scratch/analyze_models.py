#!/usr/bin/env python3
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()
api.login()

combos = api.get_combos()
models_in_combos = set()
for c in combos:
    if c.get('name'):
        for m in c.get('models', []):
            models_in_combos.add(m.get('model'))

print(f"Models in combos ({len(models_in_combos)}):")
for m in sorted(models_in_combos):
    print(f"  {m}")

# Check catalog
models = api.list_models()
model_names = {m['id'] for m in models}
print(f"\nModels in catalog: {len(model_names)}")
print("\nMissing from catalog:")
for m in sorted(models_in_combos - model_names):
    print(f"  {m}")

save_json('combo_models_analysis.json', {
    'in_combos': sorted(models_in_combos),
    'in_catalog': len(model_names),
    'missing': sorted(models_in_combos - model_names),
})
