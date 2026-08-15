import json
import re
from pathlib import Path

def main():
    print("=== Updating Zed with Healthy Models Only ===")
    
    verify_file = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\verification_results.md")
    if not verify_file.exists():
        print("Error: verification_results.md not found")
        return
        
    content = verify_file.read_text(encoding="utf-8")
    
    # Parse passed models
    passed_section = False
    healthy_models = set()
    for line in content.splitlines():
        if line.startswith("## ✅ Healthy Models"):
            passed_section = True
            continue
        elif line.startswith("## ❌ Failed Models"):
            break
            
        if passed_section and line.startswith("- `"):
            # Extract model ID: - `model/name` (Latency: ...
            match = re.search(r'- `([^`]+)`', line)
            if match:
                healthy_models.add(match.group(1))
                
    models = []
    
    # Always include aliases first
    models.append({"name": "frontier", "display_name": "⭐ OmniRoute Frontier Max", "max_tokens": 128000})
    models.append({"name": "auto/pro-coding", "display_name": "⭐ OmniRoute Pro Coding", "max_tokens": 128000})
    models.append({"name": "auto/best-fast", "display_name": "⭐ OmniRoute Best Fast", "max_tokens": 32000})
    
    # Add healthy models
    for m in sorted(list(healthy_models)):
        models.append({
            "name": m,
            "display_name": f"👑 {m}",
            "max_tokens": 128000
        })
        
    print(f"Extracted {len(healthy_models)} healthy models.")

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
        
    print(f"Successfully updated Zed settings with {len(models)} total entries (3 aliases + {len(healthy_models)} healthy models).")

if __name__ == "__main__":
    main()
