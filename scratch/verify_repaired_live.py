import requests
import json
import time

print("=== VERIFYING REPAIRED CASCADES VIA STREAMING CHAT COMPLETIONS ===")
for model in ["frontier", "auto/pro-coding", "auto/free-chat", "zai-web/glm-5.2", "github/gpt-4o"]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with 'MONETIZER OPERATIONAL'"}],
        "max_tokens": 15,
        "stream": True
    }
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, stream=True, timeout=10)
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
        elapsed = round(time.time() - start, 2)
        full_text = "".join(chunks).strip()
        print(f"[PASS] Model: {model:<20} | Status: {resp.status_code} | TTFT: {ttft}s | Total: {elapsed}s | Text: '{full_text}'")
    except Exception as e:
        print(f"[FAIL] Model: {model:<20} | Error: {str(e)[:80]}")
