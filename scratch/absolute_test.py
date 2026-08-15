import requests
import time
import json
import sys

models_to_test = {
    "kimi-coding": "kimi-coding/kimi-coding-default",
    "amazon-q": "amazon-q/amazon-q-default",
    "antigravity": "antigravity/gemini-1.5-pro",
    "cline": "cline/cline-default",
    "clinepass": "clinepass/clinepass-default",
    "github": "github/gpt-4o",
    "grok-cli": "grok-cli/default",
    "kilocode": "kilocode/gpt-4o",
    "kiro": "kiro/gpt-4o",
    "codex": "codex/gpt-5.6-sol",
    "qoder": "qoder/qwen3.7-max",
    "windsurf": "windsurf/windsurf-default",
    "zai-web": "zai-web/glm-5.2",
    "lmarena": "lmarena/claude-sonnet-5",
    "agnes": "agnes/agnes-2.0-flash",
    "ainative": "ainative/claude-3-sonnet",
    "aion": "aion/aion-labs/aion-2.0",
    "alibaba": "alibaba/qwen3.7-plus",
    "nara": "nara/mistral-large",
    "cerebras": "cerebras/gpt-oss-120b",
    "cloudflare-ai": "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct",
    "cohere": "cohere/c4ai-aya-expanse-32b"
}

healthy_models = []

print("--- TESTING ALL 22 REAL MODELS FOR THE CONFIGURED PROVIDERS ---")
for provider, model_name in models_to_test.items():
    print(f"Testing {model_name}...")
    
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Ping. Reply 'pong'."}],
        "stream": False,
        "max_tokens": 5
    }
    
    start = time.time()
    try:
        resp = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=20)
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            print(f"  [PASS] {model_name} responded in {elapsed:.2f}s")
            healthy_models.append({
                "id": model_name,
                "name": f"{model_name.split('/')[-1]} ({provider})"
            })
        else:
            print(f"  [FAIL] {model_name} HTTP {resp.status_code}: {resp.text[:80]}")
    except Exception as e:
        print(f"  [ERROR] {model_name} timed out or failed: {e}")

print("\n--- FINAL LIST OF WORKING MODELS ---")
for hm in healthy_models:
    print(f"✅ {hm['id']}")

# Update Zed settings
settings_path = r"C:\Users\Admin\AppData\Roaming\Zed\settings.json"
try:
    with open(settings_path, 'r', encoding='utf-8') as f:
        settings = json.load(f)
        
    available_models = []
    for m in healthy_models:
        available_models.append({
            "name": m["id"],
            "display_name": f"✅ {m['name']}",
            "max_tokens": 128000,
            "max_output_tokens": 8192,
            "max_completion_tokens": 128000,
            "capabilities": {
                "tools": True,
                "images": True,
                "parallel_tool_calls": False,
                "prompt_cache_key": False,
                "chat_completions": True,
                "interleaved_reasoning": False,
                "max_tokens_parameter": False
            }
        })
        
    available_models.insert(0, {
        "name": "auto/healthy-cascade",
        "display_name": "🚀 [AUTO] Healthy Models Cascade",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": {
            "tools": True,
            "images": True,
            "parallel_tool_calls": False,
            "prompt_cache_key": False,
            "chat_completions": True,
            "interleaved_reasoning": False,
            "max_tokens_parameter": False
        }
    })

    settings["language_models"]["openai_compatible"]["OmniRoute"]["available_models"] = available_models
    
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4)
        
    print("\n[SUCCESS] Zed settings updated with the final correct models!")
    
    with open("D:/omniroute-monetizer/scratch/true_final_models.json", "w") as f:
        json.dump(healthy_models, f, indent=4)

except Exception as e:
    print(f"Failed to update Zed settings: {e}")
