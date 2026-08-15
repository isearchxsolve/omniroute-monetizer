import requests
import json
from collections import defaultdict
import re

print("Fetching healthy models to curate...")
try:
    resp = requests.get("http://localhost:20128/v1/models", timeout=60)
    resp.raise_for_status()
    models_data = resp.json()
    
    models = models_data.get("data", models_data)
        
    provider_models = defaultdict(list)
    
    # Define keywords for the "finest" models across the industry
    frontier_patterns = [
        # OpenAI
        r"gpt-4o", r"o1-preview", r"o1-mini", r"gpt-4-turbo", r"o3-",
        # Anthropic
        r"claude-3-5-sonnet", r"claude-3-opus", r"claude-3-5-haiku", r"claude-sonnet-5",
        # Google
        r"gemini-1\.5-pro", r"gemini-1\.5-flash", r"gemini-2\.0", r"gemini-exp",
        # Meta Llama
        r"llama-3\.1-405b", r"llama-3\.3-70b", r"llama-3\.1-70b", r"llama-3-70b",
        # Mistral
        r"mistral-large", r"pixtral-large",
        # DeepSeek
        r"deepseek-coder-v2", r"deepseek-v3", r"deepseek-chat",
        # Qwen
        r"qwen-2\.5-72b", r"qwen-2\.5-coder-32b", r"qwen-max", r"qwen3\.7-max", r"qwen-plus",
        # Others (Zhipu, Cohere, etc.)
        r"glm-4-plus", r"glm-5", r"command-r-plus"
    ]
    
    # We will exclude weak, small, or legacy models (like gpt-3.5, claude-instant, llama-8b)
    exclusion_patterns = [
        r"8b", r"7b", r"1b", r"3b", r"9b", r"13b", r"14b", r"34b", r"32b", r"gpt-3\.5", 
        r"claude-instant", r"claude-1", r"claude-2\.", r"gemini-1\.0", r"text-davinci"
    ]

    for m in models:
        model_id = m.get("id", "")
        # OmniRoute models typically use "provider/model_name"
        if "/" in model_id:
            provider = model_id.split("/")[0]
            model_name = "/".join(model_id.split("/")[1:])
        else:
            provider = "unknown"
            model_name = model_id
            
        # Check if it matches a frontier pattern
        model_lower = model_id.lower()
        is_finest = any(re.search(pat, model_lower) for pat in frontier_patterns)
        
        # Exclude smaller variants if they sneaked in unless it's a specific exception like Qwen Coder 32B
        is_excluded = any(re.search(pat, model_lower) for pat in exclusion_patterns)
        if "coder-32b" in model_lower:
            is_excluded = False
            
        if is_finest and not is_excluded:
            provider_models[provider].append(model_name)

    # Some healthy providers to filter
    healthy_providers = {
        'agnes', 'ainative', 'aion', 'alibaba', 'cerebras', 'clinepass', 
        'cloudflare-ai', 'cohere', 'github', 'nara', 'nvidia', 'openai', 
        'opencode', 'opencode-zen', 'openrouter', 'zai-web', 'amazon-q', 
        'antigravity', 'codex', 'grok-cli', 'kilocode', 'kimi-coding', 
        'kiro', 'lmarena'
    }
    
    report = "# 👑 Curated Frontier Models\n\n"
    report += "Here is the ultimate, curated list of the absolute best, most capable models currently available from your healthy providers. I have filtered out all the noise, legacy models, and small open-weights, leaving only the finest frontier options.\n\n"
    
    total_curated = 0
    for provider in sorted(provider_models.keys()):
        if provider not in healthy_providers:
            continue
            
        models_list = sorted(list(set(provider_models[provider]))) # unique
        if not models_list:
            continue
            
        total_curated += len(models_list)
        report += f"### {provider}\n"
        for model in models_list:
            report += f"- `{model}`\n"
        report += "\n"
        
    with open(r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\curated_models.md", "w", encoding="utf-8") as f:
        f.write(report)
        
    print(f"Successfully curated {total_curated} top-tier models from {len(provider_models)} providers.")
    
except Exception as e:
    print(f"Error curating models: {e}")
