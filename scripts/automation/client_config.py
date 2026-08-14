def configure_client_zed():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures Zed with the validated OmniRoute API URL.
    """
    settings_path = Path("~/.config/zed/settings.json").expanduser()
    if not settings_path.exists():
        print(f"Error: {settings_path} not found.")
        return
    
    settings = json.loads(settings_path.read_text())
    
    # Configure OmniRoute provider
    lm = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
    lm["OmniRoute"] = {
        "api_url": "http://localhost:20128/v1",
        "available_models": [{"name": "frontier", "display_name": "Frontier (OmniRoute)"}]
    }
    
    settings_path.write_text(json.dumps(settings, indent=4))
    print(f"Zed configured successfully at {settings_path}")

def configure_client_codex():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures Codex config.toml with OmniRoute.
    """
    config_path = Path("~/.codex/config.toml").expanduser()
    if not config_path.exists():
        print(f"Error: {config_path} not found.")
        return
    
    content = config_path.read_text()
    if "localhost:20128" not in content:
        with open(config_path, "a") as f:
            f.write(f'\n[models.omniroute]\nurl = "http://localhost:20128/v1"\n')
        print(f"Codex configured at {config_path}")
    else:
        print("Codex already configured.")

def configure_client_claude_code():
    """
    [EXECUTABLE_IDEMPOTENT_CONFIG]
    Auto-configures Claude settings with OmniRoute.
    """
    config_path = Path("~/.claude/settings.json").expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    settings = {}
    if config_path.exists():
        settings = json.loads(config_path.read_text())
        
    settings["api_url"] = "http://localhost:20128/v1"
    
    config_path.write_text(json.dumps(settings, indent=4))
    print(f"Claude Code configured at {config_path}")
