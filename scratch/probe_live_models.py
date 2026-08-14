import requests
import json
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE_URL = 'http://localhost:20128/v1'

models_to_test = [
    # Qoder models (verified free)
    ("qoder", "qwen3.8-max-preview"),
    ("qoder", "kimi-k3"),
    ("qoder", "glm-5.2"),
    ("qoder", "deepseek-v4-pro"),
    ("qoder", "deepseek-v4-flash"),
    
    # NVIDIA models (verified free)
    ("nvidia", "z-ai/glm-5.2"),
    ("nvidia", "nvidia/nemotron-3-ultra-550b-a55b"),
    
    # GitHub models (verified free)
    ("github", "github/gpt-4o"),
    ("github", "github/gpt-4o-mini"),
    
    # OpenRouter free
    ("openrouter", "openrouter/auto"),
    ("openrouter", "google/gemma-4-31b-it:free"),
    
    # Alibaba
    ("alibaba", "qwen3.7-max"),
    
    # Antigravity (Google OAuth)
    ("antigravity", "gemini-3.1-pro-preview"),
    ("antigravity", "gemini-2.5-pro"),
    
    # ZAI Web
    ("zai-web", "glm-5.2"),

    # LMArena
    ("lmarena", "claude-sonnet-5"),
    
    # OpenCode-Zen
    ("opencode-zen", "gpt-5.6-sol"),
    ("opencode-zen", "claude-sonnet-5"),
]

headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer any"
}

print("=== LIVE PROBING ALL MODELS TO FIND WORKING ZERO-COST ROUTES ===")
working_models = []
failed_models = []

for provider, model_id in models_to_test:
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5
    }
    start = time.time()
    try:
        resp = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=12)
        latency = round(time.time() - start, 2)
        if resp.status_code == 200:
            data = resp.json()
            reply = data.get('choices', [{}])[0].get('message', {}).get('content', '')
            print(f"[PASS] {model_id:<35} | Status: 200 | Latency: {latency}s | Reply: {reply.strip()[:30]}")
            working_models.append((model_id, provider, latency))
        else:
            print(f"[FAIL] {model_id:<35} | Status: {resp.status_code} | Err: {resp.text[:100]}")
            failed_models.append((model_id, provider, resp.status_code, resp.text[:100]))
    except Exception as e:
        latency = round(time.time() - start, 2)
        print(f"[TIMEOUT/ERR] {model_id:<35} | Error: {str(e)[:80]}")
        failed_models.append((model_id, provider, "TIMEOUT", str(e)[:80]))

print("\n" + "=" * 80)
print(f"SUMMARY: {len(working_models)} WORKING MODELS, {len(failed_models)} FAILED MODELS")
print("=" * 80)
for m, p, l in working_models:
    print(f"  • {m:<35} (Provider: {p}, {l}s)")

