import requests
import json
from collections import defaultdict

print("Fetching healthy models from OmniRoute...")
try:
    resp = requests.get("http://localhost:20128/v1/models", timeout=60)
    resp.raise_for_status()
    models_data = resp.json()
    
    if "data" in models_data:
        models = models_data["data"]
    else:
        models = models_data
        
    provider_models = defaultdict(list)
    
    for m in models:
        model_id = m.get("id", "")
        if "/" in model_id:
            provider = model_id.split("/")[0]
            model_name = "/".join(model_id.split("/")[1:])
        else:
            provider = "unknown"
            model_name = model_id
            
        provider_models[provider].append(model_name)

    # We list models from ALL providers that return models here
    
    report = "# 🟢 Healthy Models Available\n\n"
    report += "Here is the complete list of all currently healthy models, grouped by their provider. Note that if a provider's session is expired, its models may not show up here until you re-authenticate.\n\n"
    
    for provider in sorted(provider_models.keys()):
        models_list = sorted(provider_models[provider])
        report += f"### {provider} ({len(models_list)} models)\n"
        for model in models_list:
            report += f"- `{model}`\n"
        report += "\n"
        
    with open(r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\healthy_models.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"Successfully generated healthy models list with {len(models)} total models.")
    
except Exception as e:
    print(f"Error fetching models: {e}")
