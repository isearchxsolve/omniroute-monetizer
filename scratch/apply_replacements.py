#!/usr/bin/env python3
"""Apply model replacements to combos via OmniRoute API."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json, log

api = OmniRouteAPI()
api.login()

# Get all connections to map provider/model -> id
conns = api.get_connections()
provider_map = {}  # provider -> {model -> connection_id}
for c in conns:
    prov = c.get('provider')
    if prov not in provider_map:
        provider_map[prov] = {}

# Get all models in catalog and map them
models = api.list_models()
model_to_provider = {}  # full_model_name -> provider
for m in models:
    model_to_provider[m['id']] = m.get('provider')

log(f"Mapped {len(model_to_provider)} models", "ok")

# Replacement definitions
replacements = {
    'frontier': ['agy/gemini-2.5-flash', 'ainative/gpt-4o', 'ainative/claude-3-sonnet'],
    'auto/best-coding': ['ainative/gpt-4o', 'agy/gemini-2.5-flash', 'ainative/claude-3-sonnet'],
    'auto/best-reasoning': ['ainative/claude-3-sonnet', 'ainative/gpt-4o', 'agy/gemini-2.5-flash'],
    'auto/best-chat': ['ainative/gpt-4o-mini', 'agy/gemini-2.5-flash-lite', 'ainative/llama-3-3-70b'],
    'auto/pro-coding': ['ainative/gpt-4o', 'ainative/claude-3-sonnet', 'agy/gemini-2.5-flash'],
    'auto/pro-reasoning': ['ainative/claude-3-sonnet', 'ainative/gpt-4o', 'agy/gemini-2.5-flash'],
    'auto/pro-chat': ['ainative/gpt-4o-mini', 'ainative/claude-3-sonnet', 'agy/gemini-2.5-flash-lite'],
    'fusion-coder': ['ainative/gpt-4o', 'agy/gemini-2.5-flash', 'ainative/claude-3-sonnet'],
    'kimi-coding': ['agy/gemini-2.5-flash', 'ainative/gpt-4o', 'ainative/claude-3-sonnet'],
    'moonshotai/kimi-k3-free': ['agy/gemini-2.5-flash-lite', 'ainative/gpt-4o-mini', 'ainative/llama-3-3-70b'],
}

# Get current combos
combos = api.get_combos()
combo_map = {c['name']: c for c in combos if c.get('name')}

results = {}
for combo_name, new_models in replacements.items():
    if combo_name not in combo_map:
        log(f"{combo_name}: NOT FOUND in combos", "warn")
        results[combo_name] = {'status': 'NOT_FOUND', 'error': 'Combo not in API response'}
        continue
    
    combo = combo_map[combo_name]
    combo_id = combo.get('id')
    if not combo_id:
        log(f"{combo_name}: NO ID (orphaned?)", "warn")
        results[combo_name] = {'status': 'NO_ID', 'error': 'Combo has no id field'}
        continue
    
    # Build new models array with connection IDs
    new_model_entries = []
    for idx, model_name in enumerate(new_models):
        # Find provider for this model
        provider = model_to_provider.get(model_name)
        if not provider:
            log(f"  {model_name}: NOT IN CATALOG", "warn")
            continue
        
        # Find connection for this provider
        conn = None
        for c in conns:
            if c.get('provider') == provider and c.get('isActive'):
                conn = c
                break
        
        if not conn:
            log(f"  {model_name} ({provider}): NO ACTIVE CONNECTION", "warn")
            continue
        
        provider_id = conn['id']
        new_model_entries.append({
            'id': f"{combo_name}_{idx}",
            'kind': 'model',
            'model': model_name,
            'providerId': provider_id,
            'weight': 0,
        })
    
    if not new_model_entries:
        log(f"{combo_name}: NO VALID MODELS COULD BE MAPPED", "err")
        results[combo_name] = {'status': 'NO_MODELS', 'error': 'No valid model mappings found'}
        continue
    
    # Prepare update payload
    payload = {
        'name': combo_name,
        'models': new_model_entries,
        'strategy': combo.get('strategy', 'priority'),
        'description': combo.get('description', ''),
        'retries': combo.get('retries', 3),
        'retry_delay': combo.get('retry_delay', 1000),
        'timeout': combo.get('timeout', 30000),
    }
    
    # Apply update
    log(f"Updating {combo_name} with {len(new_model_entries)} models...", "info")
    result = api.update_combo(combo_id, payload)
    status = result.get('http_status')
    
    if status == 200:
        log(f"{combo_name}: UPDATE OK", "ok")
        results[combo_name] = {
            'status': 'UPDATED',
            'http_status': status,
            'models': new_models,
        }
    else:
        log(f"{combo_name}: UPDATE FAILED (HTTP {status})", "err")
        results[combo_name] = {
            'status': 'FAILED',
            'http_status': status,
            'error': str(result.get('body', {}))[:200],
        }

save_json('combo_updates.json', results)
print(f"\n[+] Updated {sum(1 for r in results.values() if r.get('status') == 'UPDATED')} combos")
print(f"[!] Failed {sum(1 for r in results.values() if r.get('status') == 'FAILED')} combos")
