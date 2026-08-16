import requests
import uuid
import json

s = requests.Session()
s.post('http://localhost:20128/api/auth/login', json={'password': '<REDACTED>'})
res = s.get('http://localhost:20128/api/combos').json()
combos = res if isinstance(res, list) else res.get('combos', [])
kimi_combo = [c for c in combos if isinstance(c, dict) and c.get('name') == 'kimi-coding'][0]

payload = {
    'name': 'kimi-coding',
    'models': [
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'nvidia/nemotron-3-super-120b-a12b', 'providerId': 'nvidia', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'nvidia/nemotron-nano-12b-v2-vl', 'providerId': 'nvidia', 'weight': 0},
        {'id': str(uuid.uuid4()), 'kind': 'model', 'model': 'k3', 'providerId': 'kimi-coding', 'weight': 0}
    ]
}
cid = kimi_combo['id']
r = s.put(f'http://localhost:20128/api/combos/{cid}', json=payload)
print('Update status:', r.status_code)

# Test tool calling on kimi-coding
tools_payload = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city and state"}
                },
                "required": ["location"]
            }
        }
    }
]

test_payload = {
    "model": "kimi-coding",
    "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
    "tools": tools_payload,
    "tool_choice": "auto",
    "max_tokens": 100
}

r2 = requests.post('http://localhost:20128/v1/chat/completions', json=test_payload, timeout=15)
print('Tool calling status:', r2.status_code)
if r2.status_code == 200:
    print('Success response:', r2.text[:200])
else:
    print('Error response:', r2.text[:300])
