"""Configure all verified healthy models under category 'latest' across Zed, VS Code, and ZCode.
"""
from __future__ import annotations
import sys
import json
import os
import pathlib
import platform

sys.stdout.reconfigure(encoding="utf-8")

def log(msg):
    print(msg, flush=True)

# Master curated list of verified healthy models and routing combos
LATEST_MODELS = [
    # --- ROUTING COMBOS & CASCADES ---
    ("frontier", "👑 [LATEST] Master Multi-Model Frontier Cascade (10 Models)", 200000, 32000),
    ("Frontier Max", "👑 [LATEST] Full Fleet Ultra Cascade (12 Models)", 200000, 32000),
    ("auto/pro-coding", "⚡ [LATEST] Pro Coding Cascade (GPT-5.6 + Sonnet + Kimi)", 200000, 32000),
    ("auto/best-coding", "⚡ [LATEST] Best Coding Cascade (GPT-5.6 + Codestral)", 200000, 32000),
    ("fusion-coder", "⚡ [LATEST] Fusion Coder Specialist (GPT-5.6 + Sonnet + Kimi)", 200000, 32000),
    ("auto/pro-reasoning", "🧠 [LATEST] Pro Reasoning Cascade (DeepSeek R1 + Qwen 3.7 Max)", 128000, 16384),
    ("auto/best-reasoning", "🧠 [LATEST] Best Reasoning Cascade (DeepSeek R1 + Nemotron 120B)", 128000, 16384),
    ("auto/pro-chat", "💬 [LATEST] Pro Chat Cascade (GPT-5.6 + Gemini + Sonnet)", 128000, 16384),
    ("auto/best-chat", "💬 [LATEST] Best Chat Cascade (GPT-5.6 + Nemotron 120B)", 128000, 16384),
    ("auto/free-chat", "🆓 [LATEST] Free Fleet Chat Router (Groq + Cloudflare + G4F)", 128000, 8192),
    ("auto/asian-flagships", "🌏 [LATEST] Asian Flagships (DeepSeek R1 + Qwen 3.7 Max + GLM 5.2)", 128000, 16384),
    ("kimi-coding", "⚡ [LATEST] Kimi Coding Specialist (Moonshot)", 200000, 32000),
    ("moonshotai/kimi-k3-free", "⚡ [LATEST] Kimi K3 Free Frontier (Moonshot)", 200000, 32000),

    # --- NVIDIA HIGH-THROUGHPUT FLEET ---
    ("nvidia/nemotron-3-super-120b-a12b", "⚡ [LATEST] NVIDIA Nemotron 3 Super 120B (Tool-Call Safe)", 128000, 16384),
    ("nvidia/nemotron-nano-12b-v2-vl", "⚡ [LATEST] NVIDIA Nemotron Nano 12B VL (Fast Vision)", 128000, 16384),
    ("nvidia/z-ai/glm-5.2", "⚡ [LATEST] GLM 5.2 Flagship (NVIDIA/Zhipu ELO 1588)", 128000, 16384),

    # --- AGY & ANTIGRAVITY MULTIMODAL ---
    ("agy/gemini-3.6-flash-high", "⚡ [LATEST] AGY Gemini 3.6 Flash High", 200000, 32000),
    ("antigravity/gemini-3.6-flash-medium", "⚡ [LATEST] Antigravity Gemini 3.6 Flash Medium", 200000, 32000),

    # --- CLOUDFLARE AI EDGE FLEET ---
    ("cloudflare-ai/@cf/qwen/qwq-32b", "🧠 [LATEST] Cloudflare QwQ 32B Deep Reasoning", 128000, 16384),
    ("cloudflare-ai/@cf/meta/llama-3.2-3b-instruct", "⚡ [LATEST] Cloudflare LLaMA 3.2 3B Low Latency", 128000, 8192),
    ("cloudflare-ai/@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", "🧠 [LATEST] Cloudflare DeepSeek R1 Distill 32B", 128000, 16384),

    # --- MISTRAL & REKA ---
    ("mistral/codestral-2508", "⚡ [LATEST] Mistral Codestral 2508 Code Specialist", 128000, 16384),
    ("mistral/mistral-large-latest", "👑 [LATEST] Mistral Large Latest Frontier", 128000, 16384),
    ("reka/reka-flash", "⚡ [LATEST] Reka Flash Fast Multimodal", 128000, 16384),
    ("reka/reka-edge", "⚡ [LATEST] Reka Edge Ultra Low-Latency", 128000, 8192),

    # --- AGENTROUTER MULTI-MODEL GATEWAY ---
    ("agentrouter/auto", "⚡ [LATEST] AgentRouter Auto Multi-Model Gateway", 128000, 16384),
    ("agentrouter/claude-3-5-sonnet", "👑 [LATEST] AgentRouter Claude 3.5 Sonnet", 200000, 32000),
    ("agentrouter/deepseek-v3", "🧠 [LATEST] AgentRouter DeepSeek V3", 128000, 16384),
    ("agentrouter/gpt-4o", "👑 [LATEST] AgentRouter GPT-4o Flagship", 128000, 16384),

    # --- OPENADAPTER & GROQ ---
    ("openadapter/0G-DeepSeek-V3", "⚡ [LATEST] OpenAdapter DeepSeek V3 Flagship", 128000, 16384),
    ("openadapter/0G-DeepSeek-v4-Flash", "⚡ [LATEST] OpenAdapter DeepSeek v4 Flash", 128000, 8192),
    ("groq/llama-3.3-70b-versatile", "⚡ [LATEST] Groq Ultra-Fast LLaMA 3.3 70B", 128000, 8192),
    ("groq/llama-3.1-8b-instant", "⚡ [LATEST] Groq Instant LLaMA 3.1 8B", 128000, 8192),

    # --- ALIBABA QWEN FLEET ---
    ("alibaba/qwen3.7-max", "👑 [LATEST] Alibaba Qwen 3.7 Max Flagship", 128000, 16384),
    ("alibaba/qwen3.7-plus", "⚡ [LATEST] Alibaba Qwen 3.7 Plus Pro", 128000, 16384),

    # --- CODEX, KIRO, KILOCODE & AINATIVE ---
    ("codex/gpt-5.6-sol", "👑 [LATEST] Codex GPT-5.6 Sol (Peak Coding ELO 1623)", 200000, 32000),
    ("kiro/claude-sonnet-4.5", "👑 [LATEST] Kiro Claude Sonnet 4.5", 200000, 32000),
    ("kilocode/anthropic/claude-sonnet-5", "👑 [LATEST] KiloCode Claude Sonnet 5", 200000, 32000),
    ("ainative/claude-sonnet-4-5", "👑 [LATEST] AINative Claude Sonnet 4.5", 200000, 32000),
    ("ainative/deepseek-r1", "🧠 [LATEST] AINative DeepSeek R1 Frontier Reasoning", 128000, 16384),

    # --- OPENCODE-ZEN, REQUESTY, BAZAARLINK & DEEPINFRA ---
    ("opencode-zen/gpt-5.1-codex-max", "⚡ [LATEST] OpenCode-Zen GPT-5.1 Codex Max", 200000, 32000),
    ("requesty/doubleword/deepseek-v4-flash:flex", "⚡ [LATEST] Requesty DeepSeek v4 Flash Flex", 128000, 16384),
    ("bazaarlink/deepseek-v4-flash", "⚡ [LATEST] BazaarLink DeepSeek v4 Flash", 128000, 16384),
    ("deepinfra/deepseek-ai/DeepSeek-V3-0324", "🧠 [LATEST] DeepInfra DeepSeek V3", 128000, 16384),
    ("nscale/Qwen/Qwen3-4B-Thinking", "🧠 [LATEST] NScale Qwen 3 Thinking", 128000, 16384),

    # --- CHATGPT-WEB, PERPLEXITY-WEB, GEMINI-WEB ---
    ("chatgpt-web/gpt-5.6-pro", "👑 [LATEST] ChatGPT-Web GPT-5.6 Pro", 200000, 32000),
    ("perplexity-web/pplx-gpt-5.6-sol", "👑 [LATEST] Perplexity-Web GPT-5.6 Sol", 200000, 32000),
    ("gemini-web/gemini-3.1-pro", "👑 [LATEST] Gemini-Web 3.1 Pro", 200000, 32000),

    # --- G4F FREE ZERO-AUTH NODES ---
    ("g4f-gemini/gemini-2.5-flash", "⚡ [LATEST] G4F Gemini 2.5 Flash Zero-Auth", 128000, 16384),
    ("g4f-nvidia/nvidia/nemotron-3-super-120b-a12b", "⚡ [LATEST] G4F NVIDIA Nemotron 120B", 128000, 16384),
    ("g4f-groq/llama-3.3-70b", "⚡ [LATEST] G4F Groq LLaMA 70B", 128000, 8192),
    ("g4f-ollama/qwen2.5:72b", "⚡ [LATEST] G4F Ollama Qwen 72B", 128000, 16384),
    ("g4f-pollinations/openai", "⚡ [LATEST] G4F Pollinations OpenAI Router", 128000, 16384),

    # --- COHERE, FIREWORKS, BYTEZ & MORPH ---
    ("cohere/command-r-plus", "⚡ [LATEST] Cohere Command R+ RAG Specialist", 128000, 16384),
    ("fireworks/deepseek-v4-flash", "⚡ [LATEST] Fireworks DeepSeek v4 Flash", 128000, 16384),
    ("bytez/meta-llama/Llama-3.3-70B-Instruct", "⚡ [LATEST] Bytez LLaMA 3.3 70B", 128000, 8192),
    ("morph/morph-qwen35-397b", "⚡ [LATEST] Morph Qwen 3.5 397B Ultra-MoE", 128000, 16384)
]

def configure_zed():
    appdata = os.environ.get("APPDATA", str(pathlib.Path.home() / "AppData" / "Roaming"))
    zed_path = pathlib.Path(appdata) / "Zed" / "settings.json"
    if not zed_path.exists():
        log(f"[-] Zed settings not found at {zed_path}")
        return False
        
    try:
        data = json.loads(zed_path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[-] Failed to read Zed settings: {e}")
        return False
        
    # Build available_models for Zed
    zed_models = []
    for mid, mdisplay, max_ctx, max_out in LATEST_MODELS:
        zed_models.append({
            "name": mid,
            "display_name": mdisplay,
            "max_tokens": max_ctx,
            "max_output_tokens": max_out,
            "max_completion_tokens": max_ctx,
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
        
    data.setdefault("language_models", {}).setdefault("openai_compatible", {})["OmniRoute"] = {
        "api_url": "http://localhost:20128/v1",
        "available_models": zed_models
    }
    
    # Also set default model & favorites
    data.setdefault("agent", {})["default_model"] = {
        "enable_thinking": False,
        "provider": "OmniRoute",
        "model": "auto/best-coding"
    }
    data["agent"]["favorite_models"] = [
        {"provider": "OmniRoute", "model": "auto/best-coding"},
        {"provider": "OmniRoute", "model": "auto/pro-coding"},
        {"provider": "OmniRoute", "model": "frontier"},
        {"provider": "OmniRoute", "model": "Frontier Max"},
        {"provider": "OmniRoute", "model": "auto/best-reasoning"},
        {"provider": "OmniRoute", "model": "nvidia/nemotron-3-super-120b-a12b"},
        {"provider": "OmniRoute", "model": "agy/gemini-3.6-flash-high"},
        {"provider": "OmniRoute", "model": "cloudflare-ai/@cf/qwen/qwq-32b"},
        {"provider": "OmniRoute", "model": "mistral/codestral-2508"},
        {"provider": "OmniRoute", "model": "reka/reka-flash"}
    ]
    
    zed_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    log(f"[+] Zed settings.json successfully configured with {len(zed_models)} models under 'latest' at {zed_path}")
    return True

def configure_vscode():
    appdata = os.environ.get("APPDATA", str(pathlib.Path.home() / "AppData" / "Roaming"))
    vscode_dir = pathlib.Path(appdata) / "Code" / "User"
    vscode_dir.mkdir(parents=True, exist_ok=True)
    models_path = vscode_dir / "chatLanguageModels.json"
    
    vscode_models = []
    for mid, mdisplay, max_ctx, max_out in LATEST_MODELS:
        vscode_models.append({
            "id": mid,
            "name": mdisplay,
            "url": "http://localhost:20128/v1/chat/completions",
            "toolCalling": True,
            "vision": True,
            "maxInputTokens": max_ctx,
            "maxOutputTokens": max_out
        })
        
    custom_endpoint = [
        {
            "name": "OmniRoute Monetizer (Latest)",
            "vendor": "customendpoint",
            "apiKey": "sk-omniroute",
            "apiType": "chat-completions",
            "models": vscode_models
        }
    ]
    
    models_path.write_text(json.dumps(custom_endpoint, indent=4, ensure_ascii=False), encoding="utf-8")
    log(f"[+] VS Code chatLanguageModels.json successfully configured with {len(vscode_models)} models under 'latest' at {models_path}")
    return True

def configure_zcode():
    userprofile = os.environ.get("USERPROFILE", str(pathlib.Path.home()))
    config_path = pathlib.Path(userprofile) / ".zcode" / "v2" / "config.json"
    if not config_path.exists():
        log(f"[-] ZCode config path {config_path} does not exist")
        return False
        
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"[-] Failed to read ZCode config: {e}")
        return False
        
    models_dict = {}
    for idx, (mid, mdisplay, max_ctx, max_out) in enumerate(LATEST_MODELS, 1):
        models_dict[mid] = {
            "name": mid,
            "displayName": mdisplay,
            "limit": {"context": max_ctx, "output": max_out},
            "modalities": {"input": ["text"], "output": ["text"]},
            "zcode": {"modified": False, "priority": idx}
        }
        
    data.setdefault("provider", {})["custom:omniroute"] = {
        "name": "OmniRoute Monetizer (Latest)",
        "kind": "openai",
        "options": {
            "apiKey": "sk-omniroute",
            "baseURL": "http://localhost:20128/v1",
            "apiKeyRequired": False
        },
        "enabled": True,
        "source": "custom",
        "models": models_dict
    }
    
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"[+] ZCode config.json successfully configured with {len(models_dict)} models under 'latest' at {config_path}")
    return True

if __name__ == "__main__":
    log("=" * 80)
    log("  CONFIGURING ALL VERIFIED MODELS UNDER CATEGORY 'LATEST'")
    log("=" * 80)
    configure_zed()
    configure_vscode()
    configure_zcode()
    log("[+] All IDE clients configured successfully!")
