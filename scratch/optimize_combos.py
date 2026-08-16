import requests
import json
import uuid

BASE_URL = "http://localhost:20128"
s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"password": "<REDACTED>"})

# Priority ordered target lists
coding_targets = [
    {"id": str(uuid.uuid4()), "kind": "model", "model": "llama-3.1-nemotron-nano-vl-8b-v1", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "nemotron-nano-12b-v2-vl", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.4-mini", "providerId": "opencode", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "meta-llama/llama-3.3-70b-instruct:free", "providerId": "openrouter", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.6-sol", "providerId": "openai", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "glm-5.2", "providerId": "z-ai", "weight": 0},
]

reasoning_targets = [
    {"id": str(uuid.uuid4()), "kind": "model", "model": "llama-3.1-nemotron-nano-vl-8b-v1", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "nemotron-nano-12b-v2-vl", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.4-mini", "providerId": "opencode", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "auto", "providerId": "openrouter", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "grok-4.5", "providerId": "grok-cli", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.6-sol", "providerId": "openai", "weight": 0},
]

chat_targets = [
    {"id": str(uuid.uuid4()), "kind": "model", "model": "llama-3.1-nemotron-nano-vl-8b-v1", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "nemotron-nano-12b-v2-vl", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.4-mini", "providerId": "opencode", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "auto", "providerId": "openrouter", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "grok-4.5", "providerId": "grok-cli", "weight": 0},
]

frontier_targets = [
    {"id": str(uuid.uuid4()), "kind": "model", "model": "llama-3.1-nemotron-nano-vl-8b-v1", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "nemotron-nano-12b-v2-vl", "providerId": "nvidia", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.4-mini", "providerId": "opencode", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "auto", "providerId": "openrouter", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "grok-4.5", "providerId": "grok-cli", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "gpt-5.6-sol", "providerId": "openai", "weight": 0},
    {"id": str(uuid.uuid4()), "kind": "model", "model": "glm-5.2", "providerId": "z-ai", "weight": 0},
]

combos = s.get(f"{BASE_URL}/api/combos").json().get("combos", [])
combo_map = {c.get("name"): c for c in combos if c.get("name")}

updates = {
    "auto/pro-coding": coding_targets,
    "auto/pro-reasoning": reasoning_targets,
    "auto/pro-chat": chat_targets,
    "auto/best-coding": coding_targets,
    "auto/best-reasoning": reasoning_targets,
    "auto/best-chat": chat_targets,
    "frontier": frontier_targets,
    "fusion-coder": coding_targets
}

for name, target_list in updates.items():
    if name in combo_map:
        cid = combo_map[name]["id"]
        payload = combo_map[name]
        payload["models"] = target_list
        payload["strategy"] = "priority"
        payload["retries"] = 3
        payload["retry_delay"] = 300
        payload["timeout"] = 15000
        r = s.put(f"{BASE_URL}/api/combos/{cid}", json=payload)
        print(f"Updated combo {name} ({cid}): {r.status_code}")
    else:
        new_payload = {
            "name": name,
            "models": target_list,
            "strategy": "priority",
            "description": f"Verified Live {name} Cascade",
            "retries": 3,
            "retry_delay": 300,
            "timeout": 15000
        }
        r = s.post(f"{BASE_URL}/api/combos", json=new_payload)
        print(f"Created combo {name}: {r.status_code}")

print("\nCombos optimized!")
