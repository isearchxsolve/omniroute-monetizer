import time
import requests
import json

print("=== CHECKING OMNIROUTE LIVE STATUS & LATENCY ===")
start = time.time()
try:
    resp = requests.get("http://localhost:20128/", timeout=5)
    print(f"Root endpoint (/): HTTP {resp.status_code} in {round(time.time() - start, 3)}s")
except Exception as e:
    print(f"Root endpoint error: {e}")

start = time.time()
try:
    resp = requests.get("http://localhost:20128/v1/models", timeout=10)
    elapsed = round(time.time() - start, 3)
    if resp.status_code == 200:
        models = resp.json().get("data", [])
        print(f"/v1/models: HTTP 200 in {elapsed}s | Total models: {len(models)}")
    else:
        print(f"/v1/models: HTTP {resp.status_code} in {elapsed}s | {resp.text[:100]}")
except Exception as e:
    print(f"/v1/models error: {e}")

print("\n--- TESTING CHAT COMPLETIONS ---")
test_models = ["frontier", "auto/pro-coding", "kimi-k3", "glm-5.2", "github/gpt-4o"]
for m in test_models:
    start = time.time()
    try:
        payload = {
            "model": m,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5
        }
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=10)
        elapsed = round(time.time() - start, 3)
        if resp.status_code == 200:
            content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  [SUCCESS] {m:<20} | {elapsed}s | Reply: {content.strip()[:40]}")
        else:
            print(f"  [STATUS {resp.status_code}] {m:<20} | {elapsed}s | Msg: {resp.text[:100]}")
    except Exception as e:
        print(f"  [TIMEOUT/ERR] {m:<20} | Error: {str(e)[:80]}")
