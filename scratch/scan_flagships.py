"""Scan forest model lists for flagship-class coding models (qwen3.8-max tier)."""
import json
from pathlib import Path

LISTS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_model_lists.json").read_text())

# flagship / best-in-class coding signatures
FLAGSHIP = [
    "qwen3.8-max", "qwen3-max", "qwen3.7-max", "qwen3.6-max", "qwen-max",
    "qwen3-coder", "qwen-coder", "deepseek-r1", "deepseek-v3", "deepseek-chat",
    "glm-4.6", "glm-4.7", "glm-5", "kimi-k2", "kimi-k3", "k2.5",
    "nemotron-3-super", "nemotron-ultra", "nemotron-3-ultra",
    "gpt-5", "gpt-4.1", "gpt-4o", "claude", "gemini-2.5-pro", "gemini-3",
    "grok", "llama-4", "llama-3.3-70b", "llama-3.1-70b", "mistral-large",
    "command-a", "command-r-plus", "magistral", "devstral", "codestral",
    "minimax-m2", "minimax-m1", "step-3", "kimi-latest",
]

for provider, prov_lists in LISTS.items():
    models = prov_lists[0].get("models", []) if prov_lists else []
    hits = []
    for m in models:
        low = m.lower()
        for sig in FLAGSHIP:
            if sig in low:
                hits.append(m)
                break
    print(f"\n=== {provider} ({len(models)} models) — {len(hits)} flagship hits ===")
    for h in hits[:40]:
        print(f"  {h}")
