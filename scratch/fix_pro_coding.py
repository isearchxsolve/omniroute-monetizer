import requests
import json
import uuid

BASE_URL = "http://localhost:20128"
s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"password": "<REDACTED>"})

# Let's inspect /api/combos in detail
combos_res = s.get(f"{BASE_URL}/api/combos")
combos = combos_res.json().get("combos", [])

coding_targets = [
    {"id": str(uuid.uuid4()), "kind": "model", "model": "llama-3.1-nemotron-nano-vl-8b-v1", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "nemotron-nano-12b-v2-vl", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.4-mini", "providerId": "opencode", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.6-sol", "providerId": "openai", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "glm-5.2", "providerId": "z-ai", "weight": 0},
]

# If there are combos with name 'auto/pro-coding' or description matching:
for c in combos:
    print(f"ID: {c.get('id')}, Name: {c.get('name')}, Desc: {c.get('description')}")
    if c.get("id"):
        # Test updating
        if "pro-coding" in str(c.get("name", "")) or "pro-coding" in str(c.get("description", "")):
            c["name"] = "auto/pro-coding"
            c["models"] = coding_targets
            r = s.put(f"{BASE_URL}/api/combos/{c['id']}", json=c)
            print(f"PUT {c['id']} -> {r.status_code}")

