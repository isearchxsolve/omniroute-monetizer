import requests
import uuid
import json

s = requests.Session()
s.post('http://localhost:20128/api/auth/login', json={'password': '<REDACTED>'})
res = s.get('http://localhost:20128/api/combos').json()
combos = res if isinstance(res, list) else res.get('combos', [])

all_combos_to_optimize = [
    "kimi-coding",
    "moonshotai/kimi-k3-free",
    "auto/best-coding",
    "auto/best-reasoning",
    "auto/best-chat",
    "fusion-coder",
    "frontier"
]

for cname in all_combos_to_optimize:
    existing = [c for c in combos if isinstance(c, dict) and c.get('name') == cname]
    models = [
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'nvidia/nemotron-3-super-120b-a12b', 'providerId': 'nvidia', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'nvidia/nemotron-nano-12b-v2-vl', 'providerId': 'nvidia', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'kimi-k3', 'providerId': 'ainative', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'moonshotai/kimi-k3', 'providerId': 'openrouter', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'k3', 'providerId': 'kimi-coding', 'weight': 0}
    ]
    payload = {'name': cname, 'models': models}
    
    if existing:
        cid = existing[0]['id']
        r = s.put(f'http://localhost:20128/api/combos/{cid}', json=payload)
        print(f"Optimized [{cname}]:", r.status_code)
    else:
        r = s.post('http://localhost:20128/api/combos', json=payload)
        print(f"Created [{cname}]:", r.status_code)
