import requests, json, uuid
BASE_URL = 'http://localhost:20128'
s = requests.Session()
s.post(f'{BASE_URL}/api/auth/login', json={'password': 'Keross@321'})

# 1. Fetch available models
resp = s.get(f'{BASE_URL}/api/models')
all_models = resp.json().get('models', [])
premium_models = []

for m in all_models:
    if m.get('available', True):
        name = m.get('fullModel', '').lower()
        if any(x in name for x in ['gpt-5', 'gpt-4o', 'sonnet', 'opus', 'glm-5', 'gemini-3']):
            premium_models.append(m)

print(f"Found {len(premium_models)} premium models.")

# 2. Fetch combos
resp = s.get(f'{BASE_URL}/api/combos')
combos = resp.json().get('combos', [])

for c in combos:
    c_name = c.get('name', '').lower()
    c_id = c.get('id', '')
    if 'frontier max' in c_name or 'fusion-coder' in c_name:
        print(f"Updating combo: {c.get('name')} ({c_id})")
        
        existing = c.get('models', [])
        existing_full_models = {f"{t.get('providerId')}/{t.get('model')}" for t in existing}
        
        for pm in premium_models:
            full_model = f"{pm.get('provider')}/{pm.get('model')}"
            if full_model not in existing_full_models:
                existing.append({
                    "id": str(uuid.uuid4()),
                    "kind": "model",
                    "model": pm.get('model'),
                    "providerId": pm.get('provider'),
                    "weight": 0
                })
                existing_full_models.add(full_model)
                
        # Update combo
        c['models'] = existing
        c['description'] = f"Updated by Agent with {len(existing)} premium models for parallel routing."
        
        put_resp = s.put(f"{BASE_URL}/api/combos/{c_id}", json=c)
        print(f" -> PUT status {put_resp.status_code}")
