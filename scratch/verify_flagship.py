"""Verify qwen3.8-max (the exact flagship the user uses) works on harvested keys."""
import json
from pathlib import Path

import requests

KEYS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_keys.json").read_text())

TESTS = [
    ("alibaba", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen3.8-max"),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "qwen/qwen3.8-max"),
    ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "z-ai/glm-5.2:free"),
    ("nvidia", "https://integrate.api.nvidia.com/v1/chat/completions", "nvidia/nemotron-3-super-120b-a12b"),
]

for provider, url, model in TESTS:
    valid = [k for k in KEYS.get(provider, {}).get("keys", []) if k.get("verify") == "valid"]
    if not valid:
        print(f"{provider}/{model}: no valid key")
        continue
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "You are a coding agent. Reply with one word: ready"}],
        "max_tokens": 64,
        "stream": False,
    }
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {valid[0]['key']}"}, json=payload, timeout=60)
        if r.status_code == 200:
            j = r.json()
            content = j.get("choices", [{}])[0].get("message", {}).get("content", "")[:60]
            print(f"{provider}/{model}: 200 OK -> {content!r}")
        else:
            print(f"{provider}/{model}: {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"{provider}/{model}: ERROR {type(e).__name__}")
