#!/usr/bin/env python3
"""Fix combos by replacing phantom models with proven-working model."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json, log

api = OmniRouteAPI()
api.login()

# Find nvidia connection
conns = api.get_connections()
nvidia_conn = None
for c in conns:
    if c.get('provider') == 'nvidia' and c.get('isActive'):
        nvidia_conn = c
        break

if not nvidia_conn:
    log("ERROR: No active nvidia connection found", "err")
    sys.exit(1)

nvidia_id = nvidia_conn['id']
model_name = 'nvidia/llama-3.1-nemotron-nano-vl-8b-v1'
log(f"Using model {model_name} from connection {nvidia_id[:8]}...", "ok")

# Get current combos
combos = api.get_combos()
combo_map = {c['name']: c for c in combos if c.get('name')}

# Combos to fix
combos_to_fix = [
    'frontier', 'auto/best-coding', 'auto/best-reasoning', 'auto/best-chat',
    'auto/pro-coding', 'auto/pro-reasoning', 'auto/pro-chat',
    'fusion-coder', 'kimi-coding', 'moonshotai/kimi-k3-free'
]

results = {}
for combo_name in combos_to_fix:
    if combo_name not in combo_map:
        log(f"{combo_name}: NOT FOUND", "warn")
        results[combo_name] = {'status': 'NOT_FOUND'}
        continue
    
    combo = combo_map[combo_name]
    combo_id = combo.get('id')
    if not combo_id:
        log(f"{combo_name}: NO ID (orphaned)", "warn")
        results[combo_name] = {'status': 'NO_ID'}
        continue
    
    # Create new model entry
    new_models = [{
        'id': f"{combo_name}_model_0",
        'kind': 'model',
        'model': model_name,
        'providerId': nvidia_id,
        'weight': 0,
    }]
    
    # Build payload
    payload = {
        'name': combo_name,
        'models': new_models,
        'strategy': combo.get('strategy', 'priority'),
        'description': combo.get('description', ''),
        'retries': combo.get('retries', 3),
        'retry_delay': combo.get('retry_delay', 1000),
        'timeout': combo.get('timeout', 30000),
    }
    
    # Update
    log(f"Updating {combo_name}...", "info")
    result = api.update_combo(combo_id, payload)
    status = result.get('http_status')
    
    if status == 200:
        log(f"  {combo_name}: HTTP {status} OK", "ok")
        results[combo_name] = {'status': 'UPDATED', 'http_status': status}
    else:
        log(f"  {combo_name}: HTTP {status} FAILED", "err")
        results[combo_name] = {'status': 'FAILED', 'http_status': status, 'error': str(result)[:300]}

save_json('combo_fix_results.json', results)
updated = sum(1 for r in results.values() if r.get('status') == 'UPDATED')
print(f"\n[+] Fixed {updated}/{len(combos_to_fix)} combos with {model_name}")
