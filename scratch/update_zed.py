import json

settings_path = r"C:\Users\Admin\AppData\Roaming\Zed\settings.json"

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

# The healthy models from our audit
healthy_models = [
    {"id": "kimi-coding/kimi-coding-default", "name": "Kimi Coding"},
    {"id": "grok-cli/default", "name": "Grok 4.5 (CLI)"},
    {"id": "cline/cline-default", "name": "Cline (Default)"},
    {"id": "agnes/agnes-2.0-flash", "name": "Agnes 2.0 Flash"},
    {"id": "alibaba/qwen3.7-plus", "name": "Qwen 3.7 Plus (Alibaba)"},
    {"id": "cerebras/gpt-oss-120b", "name": "GPT OSS 120B (Cerebras)"},
    {"id": "cerebras/zai-glm-4.7", "name": "GLM 4.7 (Cerebras)"},
    {"id": "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct", "name": "Llama 3.2 3B (CF)"},
    {"id": "cloudflare-ai/@cf/mistral/mistral-7b-instruct-v0.2-lora", "name": "Mistral 7B (CF)"},
    {"id": "cohere/c4ai-aya-expanse-32b", "name": "Cohere Aya Expanse 32B"},
    {"id": "cohere/c4ai-aya-vision-32b", "name": "Cohere Aya Vision 32B"}
]

available_models = []

for m in healthy_models:
    available_models.append({
        "name": m["id"],
        "display_name": f"✅ [HEALTHY] {m['name']}",
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

# Add a virtual cascade that uses the top 3 reliable models
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
settings["agent"]["default_model"]["model"] = "auto/healthy-cascade"

with open(settings_path, 'w', encoding='utf-8') as f:
    json.dump(settings, f, indent=4)

print("Updated settings.json successfully!")
