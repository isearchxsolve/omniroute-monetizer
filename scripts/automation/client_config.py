"""Client auto-configuration helpers for OmniRoute Monetizer.

Provides idempotent configuration for Zed, Codex, and Claude Code clients.
"""
from pathlib import Path
import json
import os
import platform


def get_settings_path(base_path: str) -> Path:
    """Get the correct settings path for the current OS."""
    if platform.system() == "Windows":
        # Windows: AppData paths
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(appdata) / base_path
    else:
        # Unix-like: ~/.config or home directory
        return Path(base_path).expanduser()


def configure_client_zed():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures Zed with the validated OmniRoute API URL and complete Frontier + Free Model Catalog.
    """
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        settings_path = Path(appdata) / "Zed" / "settings.json"
    else:
        settings_path = Path("~/.config/zed/settings.json").expanduser()
    
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    
    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}

    capabilities_template = {
        "tools": True,
        "images": True,
        "parallel_tool_calls": False,
        "prompt_cache_key": False,
        "chat_completions": True,
        "interleaved_reasoning": False,
        "max_tokens_parameter": False
    }

    available_models = [
        # Unified Auto Routers & Cascades
        {
            "name": "frontier",
            "display_name": "👑 [FREE FRONTIER] Sonnet 5 + GPT-Sol + Kimi K3 Cascade",
            "max_tokens": 200000,
            "max_output_tokens": 32000,
            "max_completion_tokens": 200000,
            "capabilities": capabilities_template
        },
        {
            "name": "auto/pro-coding",
            "display_name": "⚡ [FREE PRO CODING] GPT-5.6 Sol + Sonnet 5 + Kimi K3",
            "max_tokens": 200000,
            "max_output_tokens": 32000,
            "max_completion_tokens": 200000,
            "capabilities": capabilities_template
        },
        {
            "name": "auto/free-chat",
            "display_name": "🆓 [FREE] Auto Free Router (Zero Cost)",
            "max_tokens": 128000,
            "max_output_tokens": 8192,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },

        # Top Frontier Models
        {
            "name": "claude-sonnet-5",
            "display_name": "👑 [FREE] Claude Sonnet 5 (Anthropic Next-Gen)",
            "max_tokens": 200000,
            "max_output_tokens": 32000,
            "max_completion_tokens": 200000,
            "capabilities": capabilities_template
        },
        {
            "name": "gpt-5.6-sol",
            "display_name": "👑 [FREE] GPT-5.6 Sol (Peak Coding ELO 1623)",
            "max_tokens": 200000,
            "max_output_tokens": 32000,
            "max_completion_tokens": 200000,
            "capabilities": capabilities_template
        },
        {
            "name": "kimi-k3",
            "display_name": "👑 [FREE] Kimi K3 (200k Frontier ELO 1674)",
            "max_tokens": 200000,
            "max_output_tokens": 32000,
            "max_completion_tokens": 200000,
            "capabilities": capabilities_template
        },
        {
            "name": "qwen3.8-max-preview",
            "display_name": "👑 [FREE] Qwen 3.8 Max Preview (Alibaba ELO 1671)",
            "max_tokens": 128000,
            "max_output_tokens": 16384,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },
        {
            "name": "glm-5.2",
            "display_name": "👑 [FREE] GLM 5.2 Flagship (Zhipu ELO 1588)",
            "max_tokens": 128000,
            "max_output_tokens": 16384,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },
        {
            "name": "deepseek-v4-pro",
            "display_name": "👑 [FREE] DeepSeek V4 Pro (Frontier Architecture)",
            "max_tokens": 128000,
            "max_output_tokens": 16384,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },
        {
            "name": "deepseek-ai/deepseek-r1",
            "display_name": "👑 [FREE] DeepSeek R1 (Frontier Reasoning)",
            "max_tokens": 128000,
            "max_output_tokens": 16384,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },
        {
            "name": "nvidia/nemotron-3-ultra-550b-a55b",
            "display_name": "👑 [FREE] Nemotron 3 Ultra 550B (NVIDIA MoE Giant)",
            "max_tokens": 128000,
            "max_output_tokens": 16384,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },
        {
            "name": "github/gpt-4o",
            "display_name": "👑 [FREE] GPT-4o (GitHub Developer Free Tier)",
            "max_tokens": 128000,
            "max_output_tokens": 4096,
            "max_completion_tokens": 128000,
            "capabilities": capabilities_template
        },
        {
            "name": "gemini-3.1-pro-preview",
            "display_name": "👑 [FREE] Gemini 3.1 Pro (Google 2M Context)",
            "max_tokens": 1000000,
            "max_output_tokens": 32000,
            "max_completion_tokens": 1000000,
            "capabilities": capabilities_template
        }
    ]
    
    # Set default agent model
    settings.setdefault("agent", {})["default_model"] = {
        "enable_thinking": False,
        "provider": "OmniRoute",
        "model": "frontier"
    }

    lm = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
    lm["OmniRoute"] = {
        "api_url": "http://localhost:20128/v1",
        "available_models": available_models
    }
    
    settings_path.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"Zed configured successfully at {settings_path}")


def configure_client_codex():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures Codex config.toml with OmniRoute.
    """
    if platform.system() == "Windows":
        localappdata = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        config_path = Path(localappdata) / ".codex" / "config.toml"
    else:
        config_path = Path("~/.codex/config.toml").expanduser()
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    content = ""
    if config_path.exists():
        content = config_path.read_text(encoding="utf-8")
    
    if "localhost:20128" not in content:
        if content and not content.endswith("\n"):
            content += "\n"
        content += '[models.omniroute]\nurl = "http://localhost:20128/v1"\n'
        config_path.write_text(content, encoding="utf-8")
        print(f"Codex configured at {config_path}")
    else:
        print("Codex already configured.")


def configure_client_claude_code():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures Claude settings with OmniRoute.
    """
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        config_path = Path(appdata) / ".claude" / "settings.json"
    else:
        config_path = Path("~/.claude/settings.json").expanduser()
    
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    settings = {}
    if config_path.exists():
        try:
            settings = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
        
    settings["api_url"] = "http://localhost:20128/v1"
    
    config_path.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"Claude Code configured at {config_path}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        client = sys.argv[1]
        if client == "zed":
            configure_client_zed()
        elif client == "codex":
            configure_client_codex()
        elif client == "claude":
            configure_client_claude_code()
        else:
            print(f"Unknown client: {client}")
            print("Usage: python client_config.py [zed|codex|claude]")
    else:
        # Configure all
        print("Configuring all clients...")
        configure_client_zed()
        configure_client_codex()
        configure_client_claude_code()
