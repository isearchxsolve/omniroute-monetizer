import requests, json
BASE_URL = 'http://localhost:20128'
s = requests.Session()
s.post(f'{BASE_URL}/api/auth/login', json={'password': 'Keross@321'}, timeout=10)

resp = s.get(f'{BASE_URL}/api/combos', timeout=10)
combos = resp.json().get('combos', [])

for c in combos:
    c_name = c.get('name', '').lower()
    c_id = c.get('id', '')
    if 'frontier max' in c_name or 'fusion-coder' in c_name:
        print(f"Reverting combo: {c.get('name')}")
        
        existing = c.get('models', [])
        # Keep only the first 5 models to prevent overloading the router
        if len(existing) > 5:
            existing = existing[:5]
            
        c['models'] = existing
        c['description'] = f"Reverted to {len(existing)} models to prevent overload."
        
        try:
            put_resp = s.put(f"{BASE_URL}/api/combos/{c_id}", json=c, timeout=10)
            print(f" -> PUT status {put_resp.status_code}")
        except Exception as e:
            print(f"Error updating {c_id}: {e}")
