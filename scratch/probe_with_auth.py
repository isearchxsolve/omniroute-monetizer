import requests
import json
import time

BASE_URL = "http://localhost:20128"
V1_URL = f"{BASE_URL}/v1"
API_KEY = "sk-2daf4dd6d1e45047-d60156-541a3aeb"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

candidate_samples = [
    "auto/pro-chat",
    "auto/best-coding",
    "auto/best-chat",
    "nvidia/nemotron-nano-12b-v2-vl",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "grok-cli/grok-4.5",
    "fusion-coder",
    "trae/work",
    "trae/gemini-3-flash-solo",
    "trae/kimi-k2.5",
    "agy/gemini-2.5-flash",
    "agy/claude-sonnet-4-6",
    "zai-web/glm-5.2"
]

print("\n--- Probing Candidate Models With API Key ---")
for model in candidate_samples:
    try:
        t0 = time.time()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Respond with OK"}],
            "max_tokens": 10,
            "temperature": 0
        }
        res = requests.post(f"{V1_URL}/chat/completions", json=payload, headers=headers, timeout=20)
        elapsed = round(time.time() - t0, 3)
        if res.status_code == 200:
            res_json = res.json()
            content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            resp_model = res_json.get("model", model)
            print(f"[OK 200] {model} -> {resp_model} ({elapsed}s): {content.strip()!r}")
        else:
            print(f"[FAIL {res.status_code}] {model} ({elapsed}s): {res.text[:100]}")
    except Exception as e:
        print(f"[ERROR] {model}: {e}")
