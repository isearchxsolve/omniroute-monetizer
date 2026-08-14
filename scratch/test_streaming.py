import requests
import json
import time

models_to_stream = [
    "github/gpt-4o-mini",
    "github/gpt-4o",
    "nvidia/nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/deepseek-ai/deepseek-r1",
    "nvidia/z-ai/glm-5.2",
    "cerebras/zai-glm-4.7",
    "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct",
    "cohere/c4ai-aya-expanse-32b",
    "zai-web/glm-5.2",
]

print("=== STREAMING INFERENCE PROBE ===")
for m in models_to_stream:
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 5,
        "stream": True
    }
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, stream=True, timeout=8)
        first_chunk_time = None
        chunks = []
        for line in resp.iter_lines():
            if line:
                if first_chunk_time is None:
                    first_chunk_time = round(time.time() - start, 2)
                chunks.append(line.decode('utf-8', errors='replace'))
                if len(chunks) >= 3:
                    break
        elapsed = round(time.time() - start, 2)
        if resp.status_code == 200 and chunks:
            print(f"[STREAM OK] {m:<45} | TTFT: {first_chunk_time}s | Total: {elapsed}s | Chunks: {len(chunks)}")
        else:
            print(f"[{resp.status_code}] {m:<45} | {elapsed}s | {resp.text[:60] if not chunks else chunks[0][:60]}")
    except Exception as e:
        print(f"[TIMEOUT] {m:<45} | {round(time.time()-start, 2)}s")
