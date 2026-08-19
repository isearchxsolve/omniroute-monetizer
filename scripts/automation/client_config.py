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


def configure_client_zcode():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures ZCode client (C:/Users/Admin/.zcode/v2/config.json) with OmniRoute custom provider and master combos.
    """
    userprofile = os.environ.get("USERPROFILE", str(Path.home()))
    config_path = Path(userprofile) / ".zcode" / "v2" / "config.json"
    
    if not config_path.exists():
        print(f"[-] ZCode config path {config_path} does not exist")
        return False

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[-] Failed to read ZCode config {config_path}: {e}")
        return False

    master_models = [
        ("frontier", "👑 [FREE FRONTIER] GPT-5.6 Sol + Sonnet 5 + Opus 4 + R1 Cascade", 1),
        ("auto/pro-coding", "⚡ [FREE PRO CODING] GPT-5.6 Sol + Sonnet 5 + Kimi K3", 2),
        ("auto/best-coding", "⚡ [FREE BEST CODING] GPT-5.6 Sol + Sonnet 5 + Codestral", 3),
        ("fusion-coder", "⚡ [FREE FUSION CODER] GPT-5.6 Sol + Sonnet 5 + Kimi K3", 4),
        ("auto/pro-reasoning", "🧠 [FREE PRO REASONING] GPT-5.6 Sol + DeepSeek R1 + Qwen 3.7 Max", 5),
        ("auto/pro-chat", "💬 [FREE PRO CHAT] GPT-5.6 Sol + Sonnet 5 + Gemini 2.5 Pro", 6),
        ("auto/best-chat", "💬 [FREE BEST CHAT] GPT-5.6 Sol + Sonnet 5 + Nemotron 120B", 7),
        ("auto/free-chat", "🆓 [FREE CHAT ROUTER] GPT-5.6 Sol + Sonnet 5 + Groq 70B", 8),
        ("auto/asian-flagships", "🌏 [FREE ASIAN FLAGSHIPS] DeepSeek R1 + Qwen 3.7 Max + GLM 5.2", 9),
        ("codex/gpt-5.6-sol", "👑 [FREE] GPT-5.6 Sol (Peak Coding ELO 1623)", 10),
        ("ainative/claude-sonnet-4-5", "👑 [FREE] Claude Sonnet 4.5 (Anthropic Flagship)", 11),
        ("ainative/deepseek-r1", "🧠 [FREE] DeepSeek R1 (Frontier Reasoning)", 12),
        ("nvidia/nemotron-3-super-120b-a12b", "⚡ [FREE] Nemotron 3 Super 120B (NVIDIA Low-Latency)", 13),
    ]

    models_dict = {}
    for name, display_name, priority in master_models:
        models_dict[name] = {
            "name": name,
            "displayName": display_name,
            "limit": {"context": 200000, "output": 32000},
            "modalities": {"input": ["text"], "output": ["text"]},
            "zcode": {"modified": False, "priority": priority},
        }

    omniroute_provider = {
        "name": "OmniRoute Monetizer",
        "kind": "openai",
        "options": {
            "apiKey": "sk-omniroute",
            "baseURL": "http://localhost:20128/v1",
            "apiKeyRequired": False,
        },
        "enabled": True,
        "source": "custom",
        "models": models_dict,
    }

    data.setdefault("provider", {})["custom:omniroute"] = omniroute_provider
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] ZCode configured successfully at {config_path}")
    return True


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


def configure_client_vscode():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures VS Code (%APPDATA%/Code/User/chatLanguageModels.json & settings.json)
    with OmniRoute base URL, custom endpoints, and all master combos + top models.
    """
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        vscode_dir = Path(appdata) / "Code" / "User"
    else:
        vscode_dir = Path("~/.config/Code/User").expanduser()

    vscode_dir.mkdir(parents=True, exist_ok=True)
    models_path = vscode_dir / "chatLanguageModels.json"

    master_models = [
        ("frontier", "👑 [FREE FRONTIER] GPT-5.6 Sol + Sonnet 5 + Opus 4 + R1 Cascade"),
        ("Frontier Max", "👑 [FREE FRONTIER MAX] Full Fleet Ultra Cascade"),
        ("auto/pro-coding", "⚡ [FREE PRO CODING] GPT-5.6 Sol + Sonnet 5 + Kimi K3"),
        ("auto/best-coding", "⚡ [FREE BEST CODING] GPT-5.6 Sol + Sonnet 5 + Codestral"),
        ("fusion-coder", "⚡ [FREE FUSION CODER] GPT-5.6 Sol + Sonnet 5 + Kimi K3"),
        ("auto/pro-reasoning", "🧠 [FREE PRO REASONING] GPT-5.6 Sol + DeepSeek R1 + Qwen 3.7 Max"),
        ("auto/best-reasoning", "🧠 [FREE BEST REASONING] GPT-5.6 Sol + DeepSeek R1"),
        ("auto/pro-chat", "💬 [FREE PRO CHAT] GPT-5.6 Sol + Sonnet 5 + Gemini 2.5 Pro"),
        ("auto/best-chat", "💬 [FREE BEST CHAT] GPT-5.6 Sol + Sonnet 5 + Nemotron 120B"),
        ("auto/free-chat", "🆓 [FREE CHAT ROUTER] GPT-5.6 Sol + Sonnet 5 + Groq 70B"),
        ("auto/asian-flagships", "🌏 [FREE ASIAN FLAGSHIPS] DeepSeek R1 + Qwen 3.7 Max + GLM 5.2"),
        ("codex/gpt-5.6-sol", "👑 [FREE] GPT-5.6 Sol (Peak Coding ELO 1623)"),
        ("ainative/claude-sonnet-4-5", "👑 [FREE] Claude Sonnet 4.5 (Anthropic Flagship)"),
        ("ainative/deepseek-r1", "🧠 [FREE] DeepSeek R1 (Frontier Reasoning)"),
        ("nvidia/nemotron-3-super-120b-a12b", "⚡ [FREE] Nemotron 3 Super 120B (NVIDIA Low-Latency)"),
    ]

    vscode_models = []
    for mid, mname in master_models:
        vscode_models.append({
            "id": mid,
            "name": mname,
            "url": "http://localhost:20128/v1/chat/completions",
            "toolCalling": True,
            "vision": True,
            "maxInputTokens": 200000,
            "maxOutputTokens": 32000
        })

    custom_endpoint = [
        {
            "name": "OmniRoute Monetizer",
            "vendor": "customendpoint",
            "apiKey": "sk-omniroute",
            "apiType": "chat-completions",
            "models": vscode_models
        }
    ]

    models_path.write_text(json.dumps(custom_endpoint, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"[+] VS Code chatLanguageModels.json configured successfully at {models_path}")
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        client = sys.argv[1]
        if client == "zcode":
            configure_client_zcode()
        elif client == "vscode":
            configure_client_vscode()
        elif client == "codex":
            configure_client_codex()
        else:
            print(f"Unknown client: {client}")
            print("Usage: python client_config.py [zcode|vscode|codex]")
    else:
        print("Configuring all clients...")
        configure_client_zcode()
        configure_client_vscode()
        configure_client_codex()
