import requests
import json
import time

test_calls = [
    # Alibaba
    ("alibaba", "qwen3.7-max"),
    ("alibaba", "qwen3.7-plus"),
    
    # Cerebras
    ("cerebras", "zai-glm-4.7"),
    
    # Cloudflare
    ("cloudflare-ai", "@cf/meta/llama-3.2-3b-instruct"),
    
    # Cohere
    ("cohere", "c4ai-aya-expanse-32b"),
    
    # ZAI Web
    ("zai-web", "glm-5.2"),
    
    # LMArena
    ("lmarena", "amazon.nova-pro-v1:0"),
    ("lmarena", "claude-haiku-4.5"),
    
    # GitHub
    ("github", "gpt-4o"),
    ("github", "gpt-4o-mini"),
    
    # NVIDIA
    ("nvidia", "meta/llama-3.3-70b-instruct"),
    ("nvidia", "01-ai/yi-large")
]

print("=== DIRECT TARGETED MODEL INFERENCE TEST ===")
for prov, m in test_calls:
    # Test model as passed directly and with provider prefix
    for model_str in [m, f"{prov}/{m}"]:
        payload = {
            "model": model_str,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5
        }
        start = time.time()
        try:
            resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=6)
            elapsed = round(time.time() - start, 2)
            if resp.status_code == 200:
                reply = resp.json().get('choices', [{}])[0].get('message', {}).get('content', '')
                print(f"[PASS] {model_str:<40} | {elapsed}s | Reply: {reply.strip()[:30]}")
            else:
                print(f"[{resp.status_code}] {model_str:<40} | {elapsed}s | {resp.text[:60]}")
        except Exception as e:
            print(f"[TIMEOUT] {model_str:<40} | {round(time.time()-start, 2)}s")
