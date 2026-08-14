import json
from pathlib import Path
import os
import platform

def update_zed_settings():
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        settings_path = Path(appdata) / "Zed" / "settings.json"
    else:
        settings_path = Path("~/.config/zed/settings.json").expanduser()

    print(f"Reading Zed settings from: {settings_path}")
    if not settings_path.exists():
        print("Settings file does not exist!")
        return

    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    # Ensure agent default model is frontier
    settings.setdefault("agent", {})["default_model"] = {
        "enable_thinking": False,
        "provider": "OmniRoute",
        "model": "frontier"
    }

    # Model catalog
    frontier_models = [
        # Unified Cascades & Auto Routers
        {"name": "frontier", "display_name": "👑 Frontier Max (Unified Cascade)", "max_tokens": 200000, "max_output_tokens": 16384},
        {"name": "auto/pro-coding", "display_name": "⚡ Pro Coding (Auto Route)", "max_tokens": 200000, "max_output_tokens": 16384},
        {"name": "auto/pro-reasoning", "display_name": "🧠 Pro Reasoning (Auto Route)", "max_tokens": 200000, "max_output_tokens": 16384},
        {"name": "auto/pro-chat", "display_name": "💬 Pro Chat (Auto Route)", "max_tokens": 200000, "max_output_tokens": 16384},
        {"name": "auto/free-chat", "display_name": "🆓 Free Chat (Zero Cost)", "max_tokens": 128000, "max_output_tokens": 8192},

        # Anthropic Claude
        {"name": "claude-opus-5-max", "display_name": "Claude Opus 5 Max (ELO 1692)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "claude-sonnet-5", "display_name": "Claude Sonnet 5 (Frontier)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "claude-opus-4.7-max", "display_name": "Claude Opus 4.7 Max", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "claude-sonnet-4.6", "display_name": "Claude Sonnet 4.6", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "claude-sonnet-4.5", "display_name": "Claude Sonnet 4.5", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "claude-haiku-4.5", "display_name": "Claude Haiku 4.5", "max_tokens": 200000, "max_output_tokens": 16384},

        # OpenAI & Codex
        {"name": "gpt-5.6-sol", "display_name": "GPT-5.6 Sol (Peak Coding ELO 1623)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "gpt-5.5", "display_name": "GPT-5.5 (Frontier Reasoning)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "gpt-5.4", "display_name": "GPT-5.4", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "gpt-5.3-codex", "display_name": "GPT-5.3 Codex", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "o3", "display_name": "o3 (Deep Reasoning)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "o1", "display_name": "o1 (Reasoning)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "gpt-4o", "display_name": "GPT-4o", "max_tokens": 128000, "max_output_tokens": 8192},

        # Google Gemini
        {"name": "gemini-3.7-flash", "display_name": "Gemini 3.7 Flash", "max_tokens": 1000000, "max_output_tokens": 32000},
        {"name": "gemini-3.6-flash", "display_name": "Gemini 3.6 Flash", "max_tokens": 1000000, "max_output_tokens": 32000},
        {"name": "gemini-3.1-pro-preview", "display_name": "Gemini 3.1 Pro Preview", "max_tokens": 1000000, "max_output_tokens": 32000},
        {"name": "gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "max_tokens": 1000000, "max_output_tokens": 32000},

        # DeepSeek
        {"name": "deepseek-v4-pro", "display_name": "DeepSeek V4 Pro", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "deepseek-v4-flash", "display_name": "DeepSeek V4 Flash", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "deepseek-v3.2", "display_name": "DeepSeek V3.2", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "deepseek-r1", "display_name": "DeepSeek R1 (Reasoning)", "max_tokens": 128000, "max_output_tokens": 16384},

        # Qwen, GLM, Kimi, Grok
        {"name": "qwen3.8-max", "display_name": "Qwen 3.8 Max (ELO 1671)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "qwen3.7-max", "display_name": "Qwen 3.7 Max", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "kimi-k3-max", "display_name": "Kimi K3 Max (ELO 1674)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "kimi-k2.7-code", "display_name": "Kimi K2.7 Code", "max_tokens": 200000, "max_output_tokens": 16384},
        {"name": "glm-5.2", "display_name": "GLM 5.2 (Flagship ELO 1588)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "grok-4.6", "display_name": "Grok 4.6 (ELO 1554)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "grok-4.5", "display_name": "Grok 4.5", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "nvidia/nemotron-3-ultra-550b-a55b", "display_name": "Nemotron 3 Ultra 550B", "max_tokens": 128000, "max_output_tokens": 16384}
    ]

    capabilities_template = {
        "tools": True,
        "images": True,
        "parallel_tool_calls": False,
        "prompt_cache_key": False,
        "chat_completions": True,
        "interleaved_reasoning": False,
        "max_tokens_parameter": False
    }

    formatted_models = []
    for m in frontier_models:
        model_entry = {
            "name": m["name"],
            "display_name": m["display_name"],
            "max_tokens": m["max_tokens"],
            "max_output_tokens": m["max_output_tokens"],
            "max_completion_tokens": m["max_tokens"],
            "capabilities": capabilities_template
        }
        formatted_models.append(model_entry)

    # Clean up redundant OmniRoute_Clone entries if desired, but keep the primary OmniRoute entry pristine
    openai_compat = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
    
    openai_compat["OmniRoute"] = {
        "api_url": "http://localhost:20128/v1",
        "available_models": formatted_models
    }

    # Clean up clutter clones if they exist
    for i in range(1, 10):
        clone_key = f"OmniRoute_Clone_{i}"
        if clone_key in openai_compat:
            del openai_compat[clone_key]

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

    print(f"Successfully configured {len(formatted_models)} frontier models in Zed settings.json!")

if __name__ == "__main__":
    update_zed_settings()
