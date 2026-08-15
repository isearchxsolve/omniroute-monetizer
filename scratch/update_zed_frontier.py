import json
import os

frontier_models = [
    # Top Tier Frontier
    {"id": "codex/gpt-5.6-sol", "name": "GPT-5.6 Sol (Codex)", "tier": "frontier"},
    {"id": "github/gpt-4o", "name": "GPT-4o (GitHub)", "tier": "frontier"},
    {"id": "kilocode/gpt-4o", "name": "GPT-4o (Kilocode)", "tier": "frontier"},
    {"id": "kiro/gpt-4o", "name": "GPT-4o (Kiro)", "tier": "frontier"},
    
    {"id": "lmarena/claude-sonnet-5", "name": "Claude 3.5 Sonnet (LM Arena)", "tier": "frontier"},
    {"id": "github/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet (GitHub)", "tier": "frontier"},
    {"id": "ainative/claude-3-sonnet", "name": "Claude 3 Sonnet (AINative)", "tier": "frontier"},
    
    {"id": "antigravity/gemini-1.5-pro", "name": "Gemini 1.5 Pro (Antigravity)", "tier": "frontier"},
    
    {"id": "qoder/qwen3.7-max", "name": "Qwen 3.7 Max (Qoder)", "tier": "frontier"},
    {"id": "alibaba/qwen3.7-max", "name": "Qwen 3.7 Max (Alibaba)", "tier": "frontier"},
    {"id": "alibaba/qwen3.7-plus", "name": "Qwen 3.7 Plus (Alibaba)", "tier": "frontier"},
    
    {"id": "zai-web/glm-5.2", "name": "GLM 5.2 (Z.ai Web)", "tier": "frontier"},
    {"id": "grok-cli/grok-4.5", "name": "Grok 4.5 (Grok CLI)", "tier": "frontier"},
    {"id": "kimi-coding/kimi-coding-default", "name": "Kimi Coding", "tier": "frontier"},
    {"id": "nara/mistral-large", "name": "Mistral Large (Nara)", "tier": "frontier"},
]

settings_path = r"C:\Users\Admin\AppData\Roaming\Zed\settings.json"

with open(settings_path, 'r', encoding='utf-8') as f:
    settings = json.load(f)

available_models = []

for m in frontier_models:
    available_models.append({
        "name": m["id"],
        "display_name": f"👑 {m['name']}",
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

# Add the cascades the user wants
cascades = [
    {
        "name": "auto/frontier",
        "display_name": "🚀 [CASCADE] Frontier Models",
        "models": ["codex/gpt-5.6-sol", "github/gpt-4o", "lmarena/claude-sonnet-5", "qoder/qwen3.7-max", "antigravity/gemini-1.5-pro"]
    },
    {
        "name": "auto/pro-coding",
        "display_name": "💻 [CASCADE] Pro Coding Models",
        "models": ["github/gpt-4o", "kilocode/gpt-4o", "lmarena/claude-sonnet-5", "kimi-coding/kimi-coding-default", "zai-web/glm-5.2"]
    }
]

for idx, c in enumerate(cascades):
    available_models.insert(idx, {
        "name": c["name"],
        "display_name": c["display_name"],
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
settings["agent"]["default_model"]["model"] = "auto/frontier"

with open(settings_path, 'w', encoding='utf-8') as f:
    json.dump(settings, f, indent=4)

print("Updated settings.json with TRUE FRONTIER models!")
