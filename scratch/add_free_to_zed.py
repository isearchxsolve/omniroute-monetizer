import json
from pathlib import Path
import os
import platform

def add_free_models_to_zed():
    appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    settings_path = Path(appdata) / "Zed" / "settings.json"
    
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    openai_compat = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
    omniroute_entry = openai_compat.setdefault("OmniRoute", {"api_url": "http://localhost:20128/v1", "available_models": []})
    
    existing_model_names = set(m["name"] for m in omniroute_entry.get("available_models", []))

    free_models_to_add = [
        # Zero cost auto router
        {"name": "auto/free-chat", "display_name": "🆓 [FREE] Auto Free Router (Zero Cost)", "max_tokens": 128000, "max_output_tokens": 8192},
        {"name": "openrouter/free", "display_name": "🆓 [FREE] OpenRouter Free Cascade", "max_tokens": 128000, "max_output_tokens": 8192},
        
        # Qoder Free Tier Flagships
        {"name": "qwen3.8-max-preview", "display_name": "🆓 [QODER] Qwen 3.8 Max Preview (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "qwen3.7-max", "display_name": "🆓 [QODER] Qwen 3.7 Max (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "kimi-k3", "display_name": "🆓 [QODER] Kimi K3 (Free)", "max_tokens": 200000, "max_output_tokens": 32000},
        {"name": "deepseek-v4-pro", "display_name": "🆓 [QODER] DeepSeek V4 Pro (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "deepseek-v4-flash", "display_name": "🆓 [QODER] DeepSeek V4 Flash (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "minimax-m3", "display_name": "🆓 [QODER] MiniMax M3 (Free)", "max_tokens": 200000, "max_output_tokens": 32000},

        # NVIDIA Free Tier Flagships
        {"name": "z-ai/glm-5.2", "display_name": "🆓 [NVIDIA] GLM 5.2 Flagship (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "nvidia/nemotron-3-ultra-550b-a55b", "display_name": "🆓 [NVIDIA] Nemotron 3 Ultra 550B (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "nvidia/nemotron-3-super-120b-a12b", "display_name": "🆓 [NVIDIA] Nemotron 3 Super 120B (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "meta/llama-3.3-70b-instruct", "display_name": "🆓 [NVIDIA] Llama 3.3 70B Instruct (Free)", "max_tokens": 128000, "max_output_tokens": 8192},
        {"name": "deepseek-ai/deepseek-r1", "display_name": "🆓 [NVIDIA] DeepSeek R1 (Free)", "max_tokens": 128000, "max_output_tokens": 16384},

        # OpenCode Zen Free Models
        {"name": "deepseek-v4-flash-free", "display_name": "🆓 [OPENCODE] DeepSeek V4 Flash (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "nemotron-3-ultra-free", "display_name": "🆓 [OPENCODE] Nemotron 3 Ultra (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "mimo-v2.5-free", "display_name": "🆓 [OPENCODE] Mimo V2.5 (Free)", "max_tokens": 128000, "max_output_tokens": 16384},
        {"name": "hy3-free", "display_name": "🆓 [OPENCODE] Tencent Hy3 (Free)", "max_tokens": 128000, "max_output_tokens": 16384},

        # OpenRouter :free models
        {"name": "google/gemma-4-31b-it:free", "display_name": "🆓 [OPENROUTER] Google Gemma 4 31B (Free)", "max_tokens": 128000, "max_output_tokens": 8192},
        {"name": "cohere/north-mini-code:free", "display_name": "🆓 [OPENROUTER] Cohere North Mini Code (Free)", "max_tokens": 128000, "max_output_tokens": 8192},
        {"name": "poolside/laguna-s-2.1:free", "display_name": "🆓 [OPENROUTER] Poolside Laguna S 2.1 (Free)", "max_tokens": 128000, "max_output_tokens": 8192},
        {"name": "openai/gpt-oss-20b:free", "display_name": "🆓 [OPENROUTER] GPT-OSS 20B (Free)", "max_tokens": 128000, "max_output_tokens": 8192},

        # GitHub Models Free Tier
        {"name": "github/gpt-4o", "display_name": "🆓 [GITHUB] GPT-4o (Free Developer Tier)", "max_tokens": 128000, "max_output_tokens": 4096},
        {"name": "github/gpt-4o-mini", "display_name": "🆓 [GITHUB] GPT-4o-mini (Free Developer Tier)", "max_tokens": 128000, "max_output_tokens": 4096},

        # Cerebras Free Speed Tier
        {"name": "cerebras/gpt-oss-120b", "display_name": "🆓 [CEREBRAS] GPT-OSS 120B (Ultra-Fast Free)", "max_tokens": 128000, "max_output_tokens": 8192}
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

    # Prepend or append new free models ensuring no duplicates
    for fm in free_models_to_add:
        if fm["name"] not in existing_model_names:
            omniroute_entry["available_models"].append({
                "name": fm["name"],
                "display_name": fm["display_name"],
                "max_tokens": fm["max_tokens"],
                "max_output_tokens": fm["max_output_tokens"],
                "max_completion_tokens": fm["max_tokens"],
                "capabilities": capabilities_template
            })
            existing_model_names.add(fm["name"])

    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

    print(f"Zed settings updated. Total models in OmniRoute: {len(omniroute_entry['available_models'])}")

if __name__ == "__main__":
    add_free_models_to_zed()
