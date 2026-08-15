import requests
import time

models_to_test = [
    "codex/gpt-5.6-sol",
    "github/gpt-4o",
    "lmarena/claude-sonnet-5",
    "qoder/qwen3.7-max",
    "antigravity/gemini-1.5-pro",
    "zai-web/glm-5.2"
]

print("--- VERIFYING MODELS AFTER RESTART ---")

for model in models_to_test:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Respond with the word 'OK' only."}]
    }
    
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=30)
        elapsed = time.time() - start
        if resp.status_code == 200:
            print(f"[PASS] {model} in {elapsed:.2f}s")
        else:
            print(f"[FAIL] {model} (HTTP {resp.status_code}): {resp.text[:150]}")
    except Exception as e:
        print(f"[ERROR] {model} timed out or failed: {e}")
