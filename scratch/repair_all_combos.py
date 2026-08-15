import requests
import json
import uuid

BASE_URL = "http://localhost:20128"
s = requests.Session()
login_res = s.post(f"{BASE_URL}/api/auth/login", json={"password": "Keross@321"})
print("Login status:", login_res.status_code)

# Fetch all available models from /api/models
models_res = s.get(f"{BASE_URL}/api/models")
all_models = models_res.json().get("models", [])
print(f"Total models available: {len(all_models)}")

# Organize models by provider/model
def find_model(provider_id, model_name):
    for m in all_models:
        if m.get("provider") == provider_id and m.get("model") == model_name:
            return m
        if m.get("provider") == provider_id and model_name in m.get("model", ""):
            return m
    return None

# Target pool definitions with verified working backends
coding_targets = [
    {"providerId": "nvidia", "model": "llama-3.1-nemotron-nano-vl-8b-v1"},
    {"providerId": "nvidia", "model": "nemotron-nano-12b-v2-vl"},
    {"providerId": "opencode", "model": "gpt-5.4-mini"},
    {"providerId": "openai", "model": "gpt-5.6-sol"},
    {"providerId": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free"},
    {"providerId": "z-ai", "model": "glm-5.2"},
]

reasoning_targets = [
    {"providerId": "grok-cli", "model": "grok-4.5"},
    {"providerId": "nvidia", "model": "nemotron-nano-12b-v2-vl"},
    {"providerId": "openai", "model": "gpt-5.6-sol"},
    {"providerId": "cohere", "model": "command-r-plus"},
    {"providerId": "cerebras", "model": "llama-3.3-70b"},
    {"providerId": "openrouter", "model": "auto"},
]

chat_targets = [
    {"providerId": "nvidia", "model": "nemotron-nano-12b-v2-vl"},
    {"providerId": "grok-cli", "model": "grok-4.5"},
    {"providerId": "opencode", "model": "gpt-5.4-mini"},
    {"providerId": "openrouter", "model": "auto"},
]

frontier_targets = [
    {"providerId": "grok-cli", "model": "grok-4.5"},
    {"providerId": "openai", "model": "gpt-5.6-sol"},
    {"providerId": "z-ai", "model": "glm-5.2"},
    {"providerId": "nvidia", "model": "nemotron-nano-12b-v2-vl"},
    {"providerId": "opencode", "model": "gpt-5.4-mini"},
]

def make_model_list(target_specs):
    result = []
    seen = set()
    for spec in target_specs:
        key = f"{spec['providerId']}/{spec['model']}"
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "id": str(uuid.uuid4()),
            "kind": "model",
            "model": spec["model"],
            "providerId": spec["providerId"],
            "weight": 0
        })
    return result

# Get existing combos
combos_res = s.get(f"{BASE_URL}/api/combos")
existing_combos = combos_res.json().get("combos", [])

combo_map = {c.get("name"): c for c in existing_combos if c.get("name")}
print("Existing named combos:", list(combo_map.keys()))

# Define desired combos
desired_combos = {
    "auto/pro-coding": {
        "models": make_model_list(coding_targets),
        "strategy": "priority",
        "description": "Verified Live Pro Coding Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "auto/pro-reasoning": {
        "models": make_model_list(reasoning_targets),
        "strategy": "priority",
        "description": "Verified Live Pro Reasoning Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "auto/pro-chat": {
        "models": make_model_list(chat_targets),
        "strategy": "priority",
        "description": "Verified Live Pro Chat Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "auto/best-coding": {
        "models": make_model_list(coding_targets),
        "strategy": "priority",
        "description": "Verified Live Best Coding Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "auto/best-reasoning": {
        "models": make_model_list(reasoning_targets),
        "strategy": "priority",
        "description": "Verified Live Best Reasoning Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "auto/best-chat": {
        "models": make_model_list(chat_targets),
        "strategy": "priority",
        "description": "Verified Live Best Chat Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "frontier": {
        "models": make_model_list(frontier_targets),
        "strategy": "priority",
        "description": "Verified Live Frontier Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    },
    "fusion-coder": {
        "models": make_model_list(coding_targets),
        "strategy": "auto",
        "description": "Verified Live Fusion Coder Cascade",
        "retries": 3,
        "retry_delay": 300,
        "timeout": 15000,
    }
}

for name, payload in desired_combos.items():
    if name in combo_map:
        cid = combo_map[name].get("id")
        existing_obj = combo_map[name]
        existing_obj.update(payload)
        r = s.put(f"{BASE_URL}/api/combos/{cid}", json=existing_obj)
        print(f"Updated combo {name} ({cid}): {r.status_code}")
    else:
        new_payload = {
            "name": name,
            **payload
        }
        r = s.post(f"{BASE_URL}/api/combos", json=new_payload)
        print(f"Created combo {name}: {r.status_code} ({r.text[:100]})")

print("\nCombos configuration complete!")
