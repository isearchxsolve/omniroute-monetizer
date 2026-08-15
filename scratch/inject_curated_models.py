import json
import os
import re
from pathlib import Path

def main():
    print("=== Injecting 135 Curated Models into Zed settings.json ===")
    
    # Read curated models
    curated_file = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\curated_models.md")
    if not curated_file.exists():
        print(f"Error: {curated_file} not found")
        return
        
    content = curated_file.read_text(encoding="utf-8")
    
    # Parse models from markdown
    models = []
    current_provider = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("### "):
            current_provider = line[4:].strip()
        elif line.startswith("- `") and line.endswith("`"):
            model_id = line[3:-1]
            if current_provider:
                # OpenRouter and other standard provider formats
                # If model_id already has a slash, we just use it directly or prepend if needed
                if current_provider == "openrouter":
                    full_id = model_id
                else:
                    full_id = f"{current_provider}/{model_id}" if "/" not in model_id else model_id
                    
                display_name = f"👑 {full_id}"
                models.append({
                    "name": full_id,
                    "display_name": display_name,
                    "max_tokens": 128000
                })
                
    # Add the core OmniRoute aliases
    models.insert(0, {"name": "frontier", "display_name": "⭐ OmniRoute Frontier Max", "max_tokens": 128000})
    models.insert(1, {"name": "auto/pro-coding", "display_name": "⭐ OmniRoute Pro Coding", "max_tokens": 128000})
    models.insert(2, {"name": "auto/best-fast", "display_name": "⭐ OmniRoute Best Fast", "max_tokens": 32000})
    
    print(f"Parsed {len(models)} models to inject.")

    # Update Zed settings
    zed_settings = Path.home() / "AppData" / "Roaming" / "Zed" / "settings.json"
    if not zed_settings.exists():
        print(f"Error: Zed settings not found at {zed_settings}")
        return
        
    with open(zed_settings, "r", encoding="utf-8") as f:
        try:
            settings = json.load(f)
        except Exception as e:
            print(f"Error parsing json: {e}")
            return
            
    # Navigate to OmniRoute config
    lm = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
    omniroute = lm.setdefault("OmniRoute", {})
    
    if "api_url" not in omniroute:
        omniroute["api_url"] = "http://localhost:20128/v1"
        
    omniroute["available_models"] = models
    
    with open(zed_settings, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
        
    print(f"Successfully injected {len(models)} models into Zed settings.json.")

if __name__ == "__main__":
    main()
