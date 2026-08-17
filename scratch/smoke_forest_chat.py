"""Smoke-test chat completions URL format for forest providers (valid payloads)."""
import json
from pathlib import Path

import requests

KEYS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_keys.json").read_text())
LISTS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_model_lists.json").read_text())

CHAT_URLS = {
    "nvidia": "https://integrate.api.nvidia.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "alibaba": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
    "opencode-zen": "https://opencode.ai/zen/v1/chat/completions",
    "llm7": "https://api.llm7.io/v1/chat/completions",
    "cohere": "https://api.cohere.com/compatibility/v1/chat/completions",
    "agnes": "https://apihub.agnes-ai.com/v1/chat/completions",
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
}

# pick a small/fast model per provider from its fetched list
PICK = {
    "nvidia": "nvidia/nemotron-nano-12b-v2-vl",
    "openrouter": None,  # pick first
    "groq": None,
    "alibaba": None,
    "opencode-zen": None,
    "llm7": None,
    "cohere": None,
    "agnes": None,
    "cerebras": None,
}


def pick_model(provider):
    if PICK.get(provider):
        return PICK[provider]
    models = LISTS.get(provider, [{}])[0].get("models", [])
    if not models:
        return None
    # prefer small/free-looking ids
    for m in models:
        low = m.lower()
        if any(t in low for t in ("free", "nano", "mini", "small", "8b", "7b", "3b")):
            return m
    return models[0]


for provider, url in CHAT_URLS.items():
    entry = KEYS.get(provider, {})
    valid = [k for k in entry.get("keys", []) if k.get("verify") == "valid"]
    if not valid:
        print(f"{provider}: no valid key, skip")
        continue
    model = pick_model(provider)
    if not model:
        print(f"{provider}: no model, skip")
        continue
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the single word: ready"}],
        "max_tokens": 32,
        "stream": False,
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {valid[0]['key']}"},
            json=payload,
            timeout=45,
        )
        body = r.text[:120].replace("\n", " ")
        print(f"{provider}: {r.status_code} model={model} | {body}")
    except Exception as e:
        print(f"{provider}: ERROR {type(e).__name__}: {e}")
