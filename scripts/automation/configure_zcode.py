#!/usr/bin/env python3
"""
ZCode Auto-Configuration Script for OmniRoute Monetizer.

Injects custom:omniroute provider and all 13 master combos + top models
directly into C:/Users/Admin/.zcode/v2/config.json.
"""
import json
import os
import sys
from pathlib import Path

ZCODE_CONFIG_PATH = Path(os.environ.get("USERPROFILE", "C:/Users/Admin")) / ".zcode" / "v2" / "config.json"

MASTER_COMBOS_AND_MODELS = [
    ("frontier", "👑 [FREE FRONTIER] GPT-5.6 Sol + Sonnet 5 + Opus 4 + R1 Cascade", 1),
    ("auto/pro-coding", "⚡ [FREE PRO CODING] GPT-5.6 Sol + Sonnet 5 + Kimi K3", 2),
    ("auto/best-coding", "⚡ [FREE BEST CODING] GPT-5.6 Sol + Sonnet 5 + Codestral", 3),
    ("fusion-coder", "⚡ [FREE FUSION CODER] GPT-5.6 Sol + Sonnet 5 + Kimi K3", 4),
    ("auto/pro-reasoning", "🧠 [FREE PRO REASONING] GPT-5.6 Sol + DeepSeek R1 + Qwen 3.7 Max", 5),
    ("auto/pro-chat", "💬 [FREE PRO CHAT] GPT-5.6 Sol + Sonnet 5 + Gemini 2.5 Pro", 6),
    ("auto/best-chat", "💬 [FREE BEST CHAT] GPT-5.6 Sol + Sonnet 5 + Nemotron 120B", 7),
    ("auto/free-chat", "🆓 [FREE CHAT ROUTER] GPT-5.6 Sol + Sonnet 5 + Groq 70B", 8),
    ("auto/asian-flagships", "🌏 [FREE ASIAN FLAGSHIPS] DeepSeek R1 + Qwen 3.7 Max + GLM 5.2", 9),
    ("codex/gpt-5.6-sol", "👑 [FREE] GPT-5.6 Sol (Peak Coding ELO 1623)", 10),
    ("ainative/claude-sonnet-4-5", "👑 [FREE] Claude Sonnet 4.5 (Anthropic Flagship)", 11),
    ("ainative/deepseek-r1", "🧠 [FREE] DeepSeek R1 (Frontier Reasoning)", 12),
    ("nvidia/nemotron-3-super-120b-a12b", "⚡ [FREE] Nemotron 3 Super 120B (NVIDIA Low-Latency)", 13),
]


def configure_zcode():
    print(f"Configuring ZCode at: {ZCODE_CONFIG_PATH}")
    if not ZCODE_CONFIG_PATH.exists():
        print(f"[-] Path {ZCODE_CONFIG_PATH} does not exist")
        return False

    try:
        data = json.loads(ZCODE_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[-] Failed to read {ZCODE_CONFIG_PATH}: {e}")
        return False

    providers = data.setdefault("provider", {})

    models_dict = {}
    for name, display_name, priority in MASTER_COMBOS_AND_MODELS:
        models_dict[name] = {
            "name": name,
            "displayName": display_name,
            "limit": {"context": 200000, "output": 32000},
            "modalities": {"input": ["text"], "output": ["text"]},
            "zcode": {"modified": False, "priority": priority},
        }

    omniroute_provider = {
        "name": "OmniRoute Monetizer",
        "kind": "openai",
        "options": {
            "apiKey": "sk-omniroute",
            "baseURL": "http://localhost:20128/v1",
            "apiKeyRequired": False,
        },
        "enabled": True,
        "source": "custom",
        "models": models_dict,
    }

    providers["custom:omniroute"] = omniroute_provider

    # Save formatted config
    ZCODE_CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[+] SUCCESS: ZCode config updated at {ZCODE_CONFIG_PATH}")
    print(f"    Added custom:omniroute provider with {len(models_dict)} models/combos")
    return True


if __name__ == "__main__":
    sys.exit(0 if configure_zcode() else 1)
