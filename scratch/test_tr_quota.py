"""Test TokenRouter quota reality: rate-limit headers + which catalog models serve.

User claim: TokenRouter is NOT quota-limited unlike NVIDIA/Groq/etc.
Evidence needed:
1. Rate-limit headers on a free-model chat completion.
2. Batch-test catalog models: 200 OK (usable) vs 403 credit (paid-only).
"""
import json
import time
from pathlib import Path

import requests

KEY = "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"  # key2
URL = "https://api.tokenrouter.com/v1/chat/completions"
CATALOG = json.loads(Path(r"d:\omniroute-monetizer\state\tokenrouter_models.json").read_text())

# 1. headers on the known-free model
r = requests.post(
    URL,
    headers={"Authorization": f"Bearer {KEY}"},
    json={
        "model": "qwen/qwen3.8-max-free",
        "messages": [{"role": "user", "content": "Reply with one word: ready"}],
        "max_tokens": 32,
        "stream": False,
    },
    timeout=60,
)
print(f"qwen3.8-max-free: {r.status_code}")
print("rate-limit headers:")
for k, v in r.headers.items():
    if "rate" in k.lower() or "limit" in k.lower() or "quota" in k.lower() or "remaining" in k.lower():
        print(f"  {k}: {v}")

# 2. batch-test a representative sample of the catalog (flagship/coding priority)
PRIORITY = [
    "qwen/qwen3.8-max", "qwen/qwen3.7-max", "qwen/qwen3-coder-next",
    "moonshotai/kimi-k2.7-code", "moonshotai/kimi-k3", "z-ai/glm-5.2", "z-ai/glm-4.7",
    "deepseek/deepseek-v3.2", "deepseek/deepseek-v4-pro",
    "anthropic/claude-sonnet-5", "anthropic/claude-opus-5",
    "openai/gpt-5.6-sol", "openai/gpt-5.5", "x-ai/grok-4.6",
    "google/gemini-3.7-flash", "nvidia/nemotron-3-super-120b-a12b",
    "minimax/minimax-m2.7", "mistralai/devstral-2512", "qwen/qwen3.6-plus",
    "xiaomi/mimo-v2.5-pro", "stepfun/step-3.7-flash", "openai/gpt-oss-120b",
    "qwen/qwen3.5-flash", "z-ai/glm-4.5-air", "openai/gpt-4o-mini",
]

usable, credit_blocked, other = [], [], []
for m in PRIORITY:
    try:
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {KEY}"},
            json={
                "model": m,
                "messages": [{"role": "user", "content": "Reply with one word: ready"}],
                "max_tokens": 32,
                "stream": False,
            },
            timeout=60,
        )
        if r.status_code == 200:
            usable.append(m)
            print(f"  OK    {m}")
        elif r.status_code == 403 and "credit" in r.text.lower():
            credit_blocked.append(m)
            print(f"  CREDIT {m}")
        else:
            other.append((m, r.status_code, r.text[:80]))
            print(f"  {r.status_code}  {m} | {r.text[:80]}")
    except Exception as e:
        other.append((m, 0, str(e)[:60]))
        print(f"  ERR   {m} {type(e).__name__}")
    time.sleep(0.3)

print(f"\nUSABLE (200 OK): {len(usable)}")
print(f"CREDIT-BLOCKED: {len(credit_blocked)}")
print(f"OTHER: {len(other)}")
Path(r"d:\omniroute-monetizer\state\tokenrouter_usable_models.json").write_text(
    json.dumps({"usable": usable, "credit_blocked": credit_blocked, "other": other}, indent=2)
)
print("saved -> state/tokenrouter_usable_models.json")
