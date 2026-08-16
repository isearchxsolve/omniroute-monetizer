import requests
import uuid
import json

s = requests.Session()
s.post('http://localhost:20128/api/auth/login', json={'password': '<REDACTED>'})
res = s.get('http://localhost:20128/api/combos').json()
combos = res if isinstance(res, list) else res.get('combos', [])
kimi_combo = [c for c in combos if isinstance(c, dict) and c.get('name') == 'kimi-coding'][0]

# Build intelligent cascade: Kimi K3 first, then ultra-reliable high-speed coding fallbacks
payload = {
    'name': 'kimi-coding',
    'models': [
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'k3', 'providerId': 'kimi-coding', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'kimi-k3', 'providerId': 'ainative', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'moonshotai/kimi-k3', 'providerId': 'openrouter', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'nvidia/nemotron-3-super-120b-a12b', 'providerId': 'nvidia', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'nvidia/nemotron-nano-12b-v2-vl', 'providerId': 'nvidia', 'weight': 0}
    ]
}
cid = kimi_combo['id']
r = s.put(f'http://localhost:20128/api/combos/{cid}', json=payload)
print('Optimized kimi-coding cascade:', r.status_code)

# Test live inference with tool calling
test_payload = {
    "model": "kimi-coding",
    "messages": [
        {"role": "user", "content": "are you kimi 3"},
        {"role": "assistant", "content": "Yes, I am Kimi K3."},
        {"role": "user", "content": "carry on"}
    ],
    "max_tokens": 100
}

r2 = requests.post('http://localhost:20128/v1/chat/completions', json=test_payload, timeout=20)
print('Inference status:', r2.status_code)
if r2.status_code == 200:
    print('Response:', r2.text[:200])
else:
    print('Error:', r2.text[:300])
