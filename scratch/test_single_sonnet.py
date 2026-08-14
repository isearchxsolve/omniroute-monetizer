import requests
import json
import time
import sys

models = [
    "ainative/claude-sonnet-4-5",
    "ainative/claude-opus-4",
    "ainative/deepseek-r1",
    "ainative/glm-5.2",
    "ainative/gpt-4o",
    "ainative/gpt-5"
]

print("=== FAST STREAMING TEST FOR AINATIVE FLAGSHIPS ===", flush=True)
for m in models:
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "1+1="}],
        "max_tokens": 5,
        "stream": True
    }
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, stream=True, timeout=5)
        chunks = []
        ttft = None
        for line in resp.iter_lines():
            if line:
                if ttft is None:
                    ttft = round(time.time() - start, 2)
                chunk_str = line.decode('utf-8', errors='replace')
                if chunk_str.startswith('data: ') and not chunk_str.startswith('data: [DONE]'):
                    chunks.append(chunk_str)
                    if len(chunks) >= 2:
                        break
        elapsed = round(time.time() - start, 2)
        if resp.status_code == 200 and chunks:
            print(f"[PASS] {m:<30} | TTFT: {ttft}s | Total: {elapsed}s | Chunks: {len(chunks)}", flush=True)
        else:
            print(f"[{resp.status_code}] {m:<30} | {elapsed}s | {resp.text[:60] if not chunks else chunks[0][:60]}", flush=True)
    except Exception as e:
        print(f"[ERR] {m:<30} | {round(time.time()-start, 2)}s | {str(e)[:60]}", flush=True)
