import requests
import json
import time

BASE_URL = "http://localhost:20128"
V1_URL = f"{BASE_URL}/v1"

s = requests.Session()
login_res = s.post(f"{BASE_URL}/api/auth/login", json={"password": "<REDACTED>"})
print("Login status:", login_res.status_code)

models_res = s.get(f"{BASE_URL}/api/models")
all_models = models_res.json().get("models", [])
print(f"Total models reported by /api/models: {len(all_models)}")

verified_working = []
failed_models = []

# Probe candidates across distinct providers
candidate_samples = [
    # nvidia
    "nvidia/nemotron-nano-12b-v2-vl",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
    "nvidia/llama-3.1-70b-instruct",
    "nvidia/deepseek-r1",
    # grok-cli
    "grok-cli/grok-4.5",
    "grok-4.5",
    # openrouter
    "openrouter/auto",
    "openrouter/meta-llama/llama-3.3-70b-instruct:free",
    # opencode
    "opencode/gpt-5.4-mini",
    # zai-web / z-ai
    "zai-web/glm-5.2",
    "z-ai/glm-5.2",
    # trae
    "trae/work",
    "trae/gemini-3-flash-solo",
    "trae/kimi-k2.5",
    # lmarena
    "lmarena/claude-sonnet-5",
    "lmarena/gpt-5.4-mini-high",
    # agy
    "agy/gemini-2.5-flash",
    "agy/claude-sonnet-4-6",
    # friendliai
    "friendli/meta-llama-3.1-8b-instruct",
    # cerebras
    "cerebras/llama-3.3-70b",
    # cohere
    "cohere/command-r-plus"
]

print("\n--- Probing Candidate Models ---")
for model in candidate_samples:
    try:
        t0 = time.time()
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Respond with OK"}],
            "max_tokens": 10,
            "temperature": 0
        }
        res = requests.post(f"{V1_URL}/chat/completions", json=payload, timeout=12)
        elapsed = round(time.time() - t0, 3)
        if res.status_code == 200:
            res_json = res.json()
            content = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            resp_model = res_json.get("model", model)
            print(f"[OK 200] {model} -> {resp_model} ({elapsed}s): {content[:30]!r}")
            verified_working.append({
                "model": model,
                "resp_model": resp_model,
                "latency": elapsed,
                "content": content
            })
        else:
            print(f"[FAIL {res.status_code}] {model} ({elapsed}s): {res.text[:80]}")
            failed_models.append((model, res.status_code, res.text[:60]))
    except Exception as e:
        print(f"[ERROR] {model}: {e}")
        failed_models.append((model, 0, str(e)))

print(f"\nSummary: {len(verified_working)} verified working, {len(failed_models)} failed.")
with open("state/healthy_probes.json", "w", encoding="utf-8") as f:
    json.dump({"verified": verified_working, "failed": failed_models}, f, indent=2)
