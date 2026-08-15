import requests
import json
import time

kimi_models = [
    "kimi-coding/k3",
    "kimi-coding/kimi-for-coding",
    "kimi-coding/kimi-for-coding-highspeed",
    "opencode-zen/kimi-k3",
    "opencode/kimi-k3",
    "clinepass/cline-pass/kimi-k3",
    "ainative/kimi-k3",
    "openrouter/moonshotai/kimi-k3"
]

print("--- TESTING KIMI K3 DIRECT ENDPOINTS ---")
for model in kimi_models:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Return 'KIMI_K3_ACTIVE'"}],
        "max_tokens": 30
    }
    t0 = time.time()
    try:
        r = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=20)
        dt = time.time() - t0
        print(f"[{model}] {r.status_code} in {dt:.2f}s -> {r.text[:120]}")
    except Exception as e:
        print(f"[{model}] Exception: {e}")
