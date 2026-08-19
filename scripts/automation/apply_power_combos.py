#!/usr/bin/env python3
"""
Re-order all OmniRoute Combos from Most Powerful Model (#1: codex/gpt-5.6-sol)
down to the least powerful model in strict capability hierarchy order.

Updates all 13 combos via PUT /api/combos/:id and verifies each combo responds 200 OK.
"""
import json
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "automation"))

from omniroute_api import OmniRouteAPI
from oauth_keepalive import resolve_password

OMNI_BASE = "http://localhost:20128"

# Model definition schema helper
def m(model_id: str, provider_id: str, weight: int) -> dict:
    return {
        "id": f"model_{provider_id}_{model_id.replace('/', '_')}",
        "kind": "model",
        "model": model_id,
        "providerId": provider_id,
        "weight": weight,
    }

# New cascade configurations: Most Powerful Model (#1: codex/gpt-5.6-sol) at the top!
COMBO_CONFIGS = {
    # 1. frontier
    "327e906d-49a5-4057-8ece-0b8c7e54850b": {
        "name": "frontier",
        "description": "Verified Frontier Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("ainative/claude-opus-4", "ainative", 90),
            m("ainative/deepseek-r1", "ainative", 85),
            m("alibaba/qwen3.7-max", "alibaba", 80),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 75),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 70),
        ],
        "strategy": "priority",
    },
    # 2. Frontier Max
    "4a4de0d2-fba6-45d4-a74d-5f06b196c300": {
        "name": "Frontier Max",
        "description": "Verified Frontier Max Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("ainative/claude-opus-4", "ainative", 90),
            m("ainative/deepseek-r1", "ainative", 85),
            m("alibaba/qwen3.7-max", "alibaba", 80),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 75),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 70),
            m("zai-web/glm-5.2", "zai-web", 65),
            m("cerebras/gpt-oss-120b", "cerebras", 60),
            m("cerebras/gemma-4-31b", "cerebras", 55),
        ],
        "strategy": "priority",
    },
    # 3. auto/pro-coding
    "66e7fa63-0bd4-4d46-b06e-3669d407459c": {
        "name": "auto/pro-coding",
        "description": "Verified Pro Coding Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
            m("alibaba/qwen3.7-plus", "alibaba", 80),
            m("zai-web/glm-5.2", "zai-web", 75),
            m("cerebras/zai-glm-4.7", "cerebras", 70),
            m("agnes/agnes-2.0-flash", "agnes", 65),
        ],
        "strategy": "priority",
    },
    # 4. auto/best-coding
    "a819dd1c-e6d5-417e-8d18-77d6399fff2e": {
        "name": "auto/best-coding",
        "description": "Verified Best Coding Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
        ],
        "strategy": "priority",
    },
    # 5. fusion-coder
    "2cae44de-8aeb-4890-958d-9087849e0e45": {
        "name": "fusion-coder",
        "description": "Verified Fusion Coder Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
        ],
        "strategy": "priority",
    },
    # 6. kimi-coding
    "02cd73d6-e809-44be-b0a1-1fa9dfe4fc5d": {
        "name": "kimi-coding",
        "description": "Verified Kimi Coding Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 95),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 90),
        ],
        "strategy": "priority",
    },
    # 7. moonshotai/kimi-k3-free
    "2e642227-70e7-4f2b-bac1-a92d7e60e079": {
        "name": "moonshotai/kimi-k3-free",
        "description": "Verified Kimi K3 Free Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 95),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 90),
        ],
        "strategy": "priority",
    },
    # 8. auto/pro-reasoning
    "f23f3d3c-9ba1-47e0-b019-923f2d64d2d4": {
        "name": "auto/pro-reasoning",
        "description": "Verified Pro Reasoning Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/deepseek-r1", "ainative", 95),
            m("alibaba/qwen3.7-max", "alibaba", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
        ],
        "strategy": "priority",
    },
    # 9. auto/best-reasoning
    "d7812773-a000-42e1-b436-ba5aabe2b7df": {
        "name": "auto/best-reasoning",
        "description": "Verified Best Reasoning Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/deepseek-r1", "ainative", 95),
            m("alibaba/qwen3.7-max", "alibaba", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
        ],
        "strategy": "priority",
    },
    # 10. auto/pro-chat
    "f13e7e40-b402-4699-8b6b-aa5bd24611d9": {
        "name": "auto/pro-chat",
        "description": "Verified Pro Chat Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("alibaba/qwen3.7-max", "alibaba", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
        ],
        "strategy": "priority",
    },
    # 11. auto/best-chat
    "191f5601-61b4-4077-8c24-104883813937": {
        "name": "auto/best-chat",
        "description": "Verified Best Chat Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 90),
        ],
        "strategy": "priority",
    },
    # 12. auto/free-chat
    "7e521395-b148-4755-903a-4d3152d44019": {
        "name": "auto/free-chat",
        "description": "Verified Free Chat Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("codex/gpt-5.6-sol", "codex", 100),
            m("ainative/claude-sonnet-4-5", "ainative", 95),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
            m("aion/aion-labs/aion-2.0", "aion", 80),
            m("amazon-q/amazon-q", "amazon-q", 75),
            m("agnes/agnes-1.5-flash", "agnes", 70),
            m("cohere/c4ai-aya-expanse-32b", "cohere", 65),
            m("cloudflare-ai/@cf/meta/llama-3.2-3b-instruct", "cloudflare-ai", 60),
        ],
        "strategy": "priority",
    },
    # 13. auto/asian-flagships
    "b12c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e": {
        "name": "auto/asian-flagships",
        "description": "Verified Asian Flagships Cascade (Most Powerful -> Least Powerful)",
        "models": [
            m("ainative/deepseek-r1", "ainative", 100),
            m("alibaba/qwen3.7-max", "alibaba", 95),
            m("kimi-coding/kimi-coding-default", "kimi-coding", 90),
            m("nvidia/nemotron-3-super-120b-a12b", "nvidia", 85),
            m("alibaba/qwen3.7-plus", "alibaba", 80),
            m("zai-web/glm-5.2", "zai-web", 75),
        ],
        "strategy": "priority",
    },
}


def apply_combo_updates():
    pw = resolve_password()
    api = OmniRouteAPI(password=pw)
    if not api.login():
        print("[-] Login failed")
        return False

    session = api.session
    print("======================================================================")
    print("RE-ORDERING ALL COMBOS: MOST POWERFUL MODEL (#1: codex/gpt-5.6-sol) -> LEAST")
    print("======================================================================")

    success_count = 0
    for cid, combo_def in COMBO_CONFIGS.items():
        name = combo_def["name"]
        print(f"Updating [{name}] ({cid[:8]})...")

        # GET existing combo to preserve config fields
        get_r = session.get(f"{OMNI_BASE}/api/combos/{cid}")
        existing = get_r.json() if get_r.ok else {}

        payload = {
            "id": cid,
            "name": name,
            "description": combo_def["description"],
            "models": combo_def["models"],
            "strategy": combo_def["strategy"],
            "config": existing.get("config", {"maxRetries": 3, "retryDelayMs": 500}),
            "isHidden": False,
        }

        put_r = session.put(f"{OMNI_BASE}/api/combos/{cid}", json=payload)
        if put_r.ok:
            print(f"  [+] SUCCESS: [{name}] updated with {len(combo_def['models'])} models in power order")
            print(f"      Top Model #1: {combo_def['models'][0]['model']}")
            success_count += 1
        else:
            print(f"  [-] FAILED [{name}]: {put_r.status_code} {put_r.text[:150]}")

    print(f"\n======================================================================")
    print(f"TOTAL COMBOS RE-ORDERED: {success_count}/{len(COMBO_CONFIGS)}")
    print("======================================================================")
    return success_count == len(COMBO_CONFIGS)


if __name__ == "__main__":
    ok = apply_combo_updates()
    sys.exit(0 if ok else 1)
