"""Verify OpenRouter :free models actually serve (24/7 zero-cost candidates)."""
import json
from pathlib import Path

import requests

KEYS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_keys.json").read_text())
LISTS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_model_lists.json").read_text())

key = [k for k in KEYS["openrouter"]["keys"] if k.get("verify") == "valid"][0]["key"]
models = LISTS["openrouter"][0]["models"]
free = [m for m in models if m.endswith(":free")]
print(f"total :free models in list: {len(free)}")

# test the flagship-class free ones
candidates = [m for m in free if any(s in m.lower() for s in
    ("glm-5", "kimi-k", "qwen3", "deepseek", "nemotron", "gpt-5", "grok", "llama-4", "mistral"))]
print(f"flagship-class free candidates: {len(candidates)}")

url = "https://openrouter.ai/api/v1/chat/completions"
ok, dead = [], []
for m in candidates[:15]:
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "Reply with one word: ready"}],
        "max_tokens": 32,
        "stream": False,
    }
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=60)
        if r.status_code == 200:
            ok.append(m)
            print(f"  OK   {m}")
        else:
            dead.append((m, r.status_code))
            print(f"  DEAD {m} -> {r.status_code}")
    except Exception as e:
        dead.append((m, type(e).__name__))
        print(f"  ERR  {m} -> {type(e).__name__}")

print(f"\nverified free+working: {len(ok)}")
