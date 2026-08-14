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
    Auto-configures Zed with the validated OmniRoute API URL.
    """
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        settings_path = Path(appdata) / "Zed" / "settings.json"
    else:
        settings_path = Path("~/.config/zed/settings.json").expanduser()
    
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    
    settings = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    
    lm = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
    lm["OmniRoute"] = {
        "api_url": "http://localhost:20128/v1",
        "available_models": [
            {
                "name": "frontier",
                "display_name": "Frontier (OmniRoute)",
                "max_tokens": 128000,
                "max_output_tokens": 8192
            },
            {
                "name": "auto/pro-coding",
                "display_name": "Pro Coding",
                "max_tokens": 128000,
                "max_output_tokens": 8192
            }
        ]
    }
    
    settings_path.write_text(json.dumps(settings, indent=4))
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
        content = config_path.read_text()
    
    if "localhost:20128" not in content:
        if content and not content.endswith("\n"):
            content += "\n"
        content += '[models.omniroute]\nurl = "http://localhost:20128/v1"\n'
        config_path.write_text(content)
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
        settings = json.loads(config_path.read_text())
        
    settings["api_url"] = "http://localhost:20128/v1"
    
    config_path.write_text(json.dumps(settings, indent=4))
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
