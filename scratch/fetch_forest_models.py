"""Fetch full model lists from all verified-valid harvested keys.

Reads state/forest_keys.json, hits each provider's /models with its valid key,
saves state/forest_model_lists.json: {provider: {key_index: [model_ids]}}.
"""
import json
from pathlib import Path

import requests

KEYS = Path(r"d:\omniroute-monetizer\state\forest_keys.json")
OUT = Path(r"d:\omniroute-monetizer\state\forest_model_lists.json")

UPSTREAM = {
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "cohere": "https://api.cohere.com/compatibility/v1",
    "llm7": "https://api.llm7.io/v1",
    "alibaba": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "aion": "https://api.aionlabs.ai/v1",
    "agnes": "https://apihub.agnes-ai.com/v1",
    "opencode-zen": "https://opencode.ai/zen/v1",
}


def main():
    data = json.loads(KEYS.read_text())
    lists = {}
    for provider, entry in data.items():
        base = UPSTREAM.get(provider)
        if not base:
            continue
        prov_lists = []
        for i, k in enumerate(entry.get("keys", [])):
            if k.get("verify") != "valid":
                continue
            try:
                r = requests.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {k['key']}"},
                    timeout=60,
                )
                ids = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
            except Exception as e:
                print(f"  {provider}[{i}]: ERROR {type(e).__name__}")
                continue
            prov_lists.append({"key_index": i, "models": ids})
            print(f"  {provider}[{i}]: {len(ids)} models")
        if prov_lists:
            lists[provider] = prov_lists
    OUT.write_text(json.dumps(lists, indent=2))
    total = sum(len(p["models"]) for pl in lists.values() for p in pl)
    uniq = len({m for pl in lists.values() for p in pl for m in p["models"]})
    print(f"\nsaved -> {OUT}")
    print(f"providers: {len(lists)}, total model entries: {total}, unique: {uniq}")


if __name__ == "__main__":
    main()
