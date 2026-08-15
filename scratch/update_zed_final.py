import json

healthy_models = [
    {"id": "kimi-coding/kimi-coding-default", "name": "Kimi Coding (Default)"},
    {"id": "github/gpt-4o", "name": "GitHub (GPT-4o)"},
    {"id": "kilocode/gpt-4o", "name": "Kilocode (GPT-4o)"},
    {"id": "agnes/agnes-2.0-flash", "name": "Agnes 2.0 Flash"},
    {"id": "ainative/claude-3-sonnet", "name": "AINative (Claude 3 Sonnet)"},
    {"id": "aion/aion-labs/aion-2.0", "name": "Aion (Aion 2.0)"},
    {"id": "alibaba/qwen3.7-plus", "name": "Alibaba (Qwen 3.7 Plus)"},
    {"id": "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct", "name": "Cloudflare (Llama 3.2 3B)"},
    {"id": "cohere/c4ai-aya-expanse-32b", "name": "Cohere (Aya Expanse 32B)"}
]

settings_path = r"C:\Users\Admin\AppData\Roaming\Zed\settings.json"

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

available_models = []

for m in healthy_models:
    available_models.append({
        "name": m["id"],
        "display_name": f"WORKING: {m['name']}",
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
    "display_name": "AUTO Healthy Cascade (Top Models)",
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
