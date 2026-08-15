import requests
import time
import json
import traceback

providers_to_test = {
    "lmarena": "lmarena/claude-sonnet-5",
    "qoder": "qoder/qwen3.7-max",
    "codex": "codex/gpt-5.6-sol",
    "grok-cli": "grok-cli/grok-4.5",
    "amazon-q": "amazon-q/amazon-q"
}

print("Starting RCA for specific providers via OmniRoute API...")

for provider, model_name in providers_to_test.items():
    print(f"\n--- Testing {provider} with model {model_name} ---")
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Hello, what model are you?"}],
        "stream": False # Try non-streaming first to get exact error body easily
    }
    
    start_time = time.time()
    try:
        # Increase timeout to 30s to rule out slow TTFT
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=30)
        elapsed = time.time() - start_time
        print(f"Status Code: {resp.status_code}")
        print(f"Elapsed Time: {elapsed:.2f}s")
        print(f"Response Headers: {dict(resp.headers)}")
        
        if resp.status_code == 200:
            print("SUCCESS! Response snippet:", resp.text[:200])
        else:
            print("FAILED. Error body:", resp.text)
            
    except Exception as e:
        print(f"Exception occurred: {e}")
        # traceback.print_exc()

print("\n--- Done RCA ---")
