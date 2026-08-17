"""Verify TokenRouter's explicitly-free models actually serve chat completions."""
import json

import requests

KEY = "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"  # key2, live
URL = "https://api.tokenrouter.com/v1/chat/completions"

FREE = [
    "qwen/qwen3.8-max-free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]

for model in FREE:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with one word: ready"}],
        "max_tokens": 32,
        "stream": False,
    }
    try:
        r = requests.post(URL, headers={"Authorization": f"Bearer {KEY}"}, json=payload, timeout=60)
        if r.status_code == 200:
            content = r.json().get("choices", [{}])[0].get("message", {}).get("content", "")[:50]
            print(f"  OK   {model} -> {content!r}")
        else:
            print(f"  DEAD {model} -> {r.status_code} {r.text[:100]}")
    except Exception as e:
        print(f"  ERR  {model} -> {type(e).__name__}")
