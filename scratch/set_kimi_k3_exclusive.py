import requests
import uuid
import json

s = requests.Session()
s.post('http://localhost:20128/api/auth/login', json={'password': '<REDACTED>'})
res = s.get('http://localhost:20128/api/combos').json()
combos = res if isinstance(res, list) else res.get('combos', [])
kimi_combo = [c for c in combos if isinstance(c, dict) and c.get('name') == 'kimi-coding'][0]

# Set ONLY pure Kimi K3 targets
payload = {
    'name': 'kimi-coding',
    'models': [
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'k3', 'providerId': 'kimi-coding', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'kimi-k3', 'providerId': 'opencode-zen', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'moonshotai/kimi-k3', 'providerId': 'openrouter', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'cline-pass/kimi-k3', 'providerId': 'clinepass', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'kimi-k3', 'providerId': 'ainative', 'weight': 0}
    ]
}
cid = kimi_combo['id']
r = s.put(f'http://localhost:20128/api/combos/{cid}', json=payload)
print('Update kimi-coding (Kimi K3 ONLY):', r.status_code, r.text[:200])
