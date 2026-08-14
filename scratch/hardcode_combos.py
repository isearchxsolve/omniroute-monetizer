import requests, json, uuid
BASE_URL = 'http://localhost:20128'
s = requests.Session()
s.post(f'{BASE_URL}/api/auth/login', json={'password': 'Keross@321'}, timeout=10)

resp = s.get(f'{BASE_URL}/api/combos', timeout=10)
combos = resp.json().get('combos', [])

safe_models = [
    {"model": "gpt-5.6-sol", "providerId": "openai"},
    {"model": "glm-5.2", "providerId": "z-ai"}
]

for c in combos:
    c_name = c.get('name', '').lower()
    c_id = c.get('id', '')
    if 'frontier max' in c_name or 'fusion-coder' in c_name:
        print(f"Hardcoding safe models into combo: {c.get('name')}")
        
        new_models = []
        for sm in safe_models:
            new_models.append({
                "id": str(uuid.uuid4()),
                "kind": "model",
                "model": sm['model'],
                "providerId": sm['providerId'],
                "weight": 0
            })
            
        c['models'] = new_models
        c['description'] = f"Safely hardcoded to GPT-5.6-Sol and GLM-5.2."
        
        try:
            put_resp = s.put(f"{BASE_URL}/api/combos/{c_id}", json=c, timeout=10)
            print(f" -> PUT status {put_resp.status_code}")
        except Exception as e:
            print(f"Error updating {c_id}: {e}")
