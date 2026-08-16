#!/usr/bin/env python3
"""Find real tool-safe models from catalog to replace phantom combo models."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()

# Get full catalog
models = api.list_models()
print(f"[*] Catalog: {len(models)} total models")

# Filter for tool-safe candidates (fast, small, likely to support tool_choice:auto)
# Heuristics: 
# - Avoid anything with "nano" in name alone (needs explicit support)
# - Prefer models from known tool-safe providers: openai, anthropic, google
# - Include fast open-source: llama, mistral, neural
# - Exclude vision-only models (unlikely to have tools)

tool_safe_keywords = {
    'gpt-4', 'gpt-3.5', 'claude-3', 'claude-2', 'gemini',
    'llama-3.1', 'llama-3', 'mistral', 'neural', 'command', 'aya'
}

exclude_keywords = {'-vision', '-vision-preview', '-vl', 'flux', 'dall-e', 
                    'whisper', 'tts', 'embedding', 'text-embedding'}

candidates = []
for m in models:
    model_id = m.get('id', '').lower()
    # Skip vision-only
    if any(ex in model_id for ex in exclude_keywords):
        continue
    # Include if matches tool-safe keywords
    if any(kw in model_id for kw in tool_safe_keywords):
        candidates.append({
            'id': m['id'],
            'provider': m.get('provider'),
            'created': m.get('created'),
        })

print(f"[+] Found {len(candidates)} tool-safe candidates")
print("\nTop candidates (by ID):")
for c in sorted(candidates, key=lambda x: x['id'])[:30]:
    print(f"  {c['id']} ({c.get('provider')})")

# Also look for any working nvidia/openai/anthropic models
print("\n[*] Checking for provider-specific models:")
for provider in ['nvidia', 'openai', 'anthropic', 'openrouter']:
    prov_models = [m['id'] for m in models if provider in m.get('provider', '').lower()]
    if prov_models:
        print(f"  {provider}: {len(prov_models)} models")
        # Show first 5
        for pm in sorted(prov_models)[:5]:
            print(f"    {pm}")

save_json('tool_safe_candidates.json', {
    'total_catalog': len(models),
    'tool_safe_candidates': candidates,
    'candidates_count': len(candidates),
})

print(f"\n[+] Full list saved to state/tool_safe_candidates.json")
