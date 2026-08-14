import requests
import json
import time

models_to_test = [
    "ainative/claude-sonnet-4-5",
    "ainative/claude-opus-4",
    "ainative/kimi-k3",
    "ainative/glm-5.2",
    "ainative/deepseek-r1",
    "ainative/deepseek-v4-pro",
    "ainative/gpt-5",
    "ainative/gpt-5-mini",
    "ainative/gpt-4o",
    "ainative/o1",
    "ainative/o3",
    "ainative/qwen3-coder-30b-a3b",
    "ainative/nemotron-3-ultra-550b"
]

print("=== LIVE PROBING ALL AINATIVE FRONTIERS ===")
for m in models_to_test:
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "1+1="}],
        "max_tokens": 5,
        "stream": True
    }
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, stream=True, timeout=8)
        chunks = []
        ttft = None
        for line in resp.iter_lines():
            if line:
                if ttft is None:
                    ttft = round(time.time() - start, 2)
                chunk_str = line.decode('utf-8', errors='replace')
                if chunk_str.startswith('data: ') and not chunk_str.startswith('data: [DONE]'):
                    try:
                        d = json.loads(chunk_str[6:])
                        delta = d.get('choices', [{}])[0].get('delta', {}).get('content', '')
                        if delta:
                            chunks.append(delta)
                    except:
                        pass
                if len(chunks) >= 2:
                    break
        elapsed = round(time.time() - start, 2)
        if resp.status_code == 200:
            print(f"[SUCCESS] {m:<32} | TTFT: {ttft}s | Total: {elapsed}s | Out: {''.join(chunks).strip()}")
        else:
            print(f"[{resp.status_code}] {m:<32} | {elapsed}s | {resp.text[:60]}")
    except Exception as e:
        print(f"[TIMEOUT/ERR] {m:<32} | {str(e)[:60]}")
