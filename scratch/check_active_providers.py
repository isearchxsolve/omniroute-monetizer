import requests, json
BASE_URL = 'http://localhost:20128'
s = requests.Session()
s.post(f'{BASE_URL}/api/auth/login', json={'password': 'Keross@321'}, timeout=10)
resp = s.get(f'{BASE_URL}/api/providers', timeout=10)
conns = resp.json().get('connections', [])
for c in conns:
    if c.get('isActive') == True:
        print(f"{c.get('id')} -> {c.get('name')}")
