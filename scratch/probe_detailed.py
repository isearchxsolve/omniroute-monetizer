import requests
import json
import time

models = [
    "z-ai/glm-5.2",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "meta/llama-3.3-70b-instruct",
    "deepseek-ai/deepseek-r1",
    "github/gpt-4o-mini",
    "qwen3.8-max-preview",
    "kimi-k3"
]

print("=== DETAILED MODEL PROBE ===")
for m in models:
    start = time.time()
    try:
        payload = {
            "model": m,
            "messages": [{"role": "user", "content": "1+1="}],
            "max_tokens": 5
        }
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=8)
        elapsed = round(time.time() - start, 2)
        print(f"[{resp.status_code}] {m:<35} | {elapsed}s | {resp.text[:80]}")
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        print(f"[ERR] {m:<35} | {elapsed}s | {str(e)[:80]}")
