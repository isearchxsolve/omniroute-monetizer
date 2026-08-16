import requests, json, uuid
BASE_URL = 'http://localhost:20128'
s = requests.Session()
s.post(f'{BASE_URL}/api/auth/login', json={'password': '<REDACTED>'}, timeout=10)

# 1. Fetch active providers
resp = s.get(f'{BASE_URL}/api/providers', timeout=10)
connections = resp.json().get('connections', [])
active_provider_ids = set()
for c in connections:
    if c.get('isActive') == True:
        active_provider_ids.add(c.get('providerId'))

print(f"Active providers: {active_provider_ids}")

# 2. Fetch available models
resp = s.get(f'{BASE_URL}/api/models', timeout=10)
all_models = resp.json().get('models', [])
premium_models = []

for m in all_models:
    # ONLY IF THE PROVIDER IS ACTIVE!
    if m.get('provider') in active_provider_ids:
        name = m.get('fullModel', '').lower()
        if any(x in name for x in ['gpt-5', 'gpt-4o', 'sonnet', 'opus', 'glm-5', 'gemini-3']):
            premium_models.append(m)

print(f"Found {len(premium_models)} premium models on ACTIVE connections.")

# 3. Update combos
resp = s.get(f'{BASE_URL}/api/combos', timeout=10)
combos = resp.json().get('combos', [])

for c in combos:
    c_name = c.get('name', '').lower()
    c_id = c.get('id', '')
    if 'frontier max' in c_name or 'fusion-coder' in c_name:
        print(f"Updating combo: {c.get('name')} ({c_id})")
        
        # WE MUST CLEAR OUT THE DEAD ONES! 
        # Don't just append, replace completely to flush out dead models!
        new_models = []
        for pm in premium_models:
            new_models.append({
                "id": str(uuid.uuid4()),
                "kind": "model",
                "model": pm.get('model'),
                "providerId": pm.get('provider'),
                "weight": 0
            })
            
        c['models'] = new_models
        c['description'] = f"Updated by Agent with {len(new_models)} verified premium models."
        
        try:
            put_resp = s.put(f"{BASE_URL}/api/combos/{c_id}", json=c, timeout=10)
            print(f" -> PUT status {put_resp.status_code}")
        except Exception as e:
            print(f"Error updating {c_id}: {e}")
