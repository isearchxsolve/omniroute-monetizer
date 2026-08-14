import sqlite3
import json
import uuid
import datetime
from pathlib import Path
import os
import platform

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"

# 1. Update OmniRoute DB combos with GPT-Sol, Sonnet-5, Kimi-K3, Qwen-3.8, GLM-5.2
print("Updating OmniRoute Database combos...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

frontier_free_models = [
    {
        "id": str(uuid.uuid4()),
        "kind": "model",
        "model": "claude-sonnet-5",
        "providerId": "opencode-zen",
        "weight": 100
    },
    {
        "id": str(uuid.uuid4()),
        "kind": "model",
        "model": "gpt-5.6-sol",
        "providerId": "opencode-zen",
        "weight": 95
    },
    {
        "id": str(uuid.uuid4()),
        "kind": "model",
        "model": "kimi-k3",
        "providerId": "qoder",
        "weight": 90
    },
    {
        "id": str(uuid.uuid4()),
        "kind": "model",
        "model": "qwen3.8-max-preview",
        "providerId": "qoder",
        "weight": 85
    },
    {
        "id": str(uuid.uuid4()),
        "kind": "model",
        "model": "glm-5.2",
        "providerId": "qoder",
        "weight": 80
    },
    {
        "id": str(uuid.uuid4()),
        "kind": "model",
        "model": "deepseek-v4-pro",
        "providerId": "qoder",
        "weight": 75
    }
]

frontier_combo_data = {
    "name": "Frontier Max",
    "models": frontier_free_models,
    "strategy": "auto",
    "config": {
        "maxRetries": 3,
        "retryDelayMs": 500,
        "handoffThreshold": 0.85,
        "handoffModel": "",
        "maxMessagesForSummary": 30,
        "trackMetrics": True
    },
    "id": "4a4de0d2-fba6-45d4-a74d-5f06b196c300",
    "isHidden": False,
    "sortOrder": 1,
    "version": 3,
    "description": "Free Frontier Cascade: Claude Sonnet 5 + GPT-5.6 Sol + Kimi K3 + Qwen 3.8 Max"
}

cursor.execute("UPDATE combos SET data = ?, updated_at = ? WHERE name = 'Frontier Max' OR id = '4a4de0d2-fba6-45d4-a74d-5f06b196c300'",
               (json.dumps(frontier_combo_data), datetime.datetime.utcnow().isoformat() + "Z"))

# Also ensure auto/free-chat and auto/pro-coding have the top free models
pro_coding_combo_id = str(uuid.uuid4())
pro_coding_data = {
    "name": "auto/pro-coding",
    "models": frontier_free_models,
    "strategy": "auto",
    "config": {
        "maxRetries": 3,
        "retryDelayMs": 500,
        "handoffThreshold": 0.85,
        "handoffModel": "",
        "maxMessagesForSummary": 30,
        "trackMetrics": True
    },
    "id": pro_coding_combo_id,
    "isHidden": False,
    "sortOrder": 2,
    "version": 1,
    "description": "Free Pro Coding: Sonnet 5 + GPT-Sol + Kimi K3"
}
cursor.execute("SELECT id FROM combos WHERE name = 'auto/pro-coding'")
if cursor.fetchone():
    cursor.execute("UPDATE combos SET data = ?, updated_at = ? WHERE name = 'auto/pro-coding'",
                   (json.dumps(pro_coding_data), datetime.datetime.utcnow().isoformat() + "Z"))
else:
    cursor.execute("INSERT INTO combos (id, name, data, sort_order, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (pro_coding_combo_id, "auto/pro-coding", json.dumps(pro_coding_data), 2, pro_coding_data["config"]["retryDelayMs"], datetime.datetime.utcnow().isoformat() + "Z"))

conn.commit()
conn.close()
print("OmniRoute DB updated with Sonnet 5, GPT-Sol, and Kimi K3!")

# 2. Update Zed settings
appdata = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
settings_path = Path(appdata) / "Zed" / "settings.json"

with open(settings_path, "r", encoding="utf-8") as f:
    settings = json.load(f)

capabilities_template = {
    "tools": True,
    "images": True,
    "parallel_tool_calls": False,
    "prompt_cache_key": False,
    "chat_completions": True,
    "interleaved_reasoning": False,
    "max_tokens_parameter": False
}

zed_free_frontiers = [
    # Primary Free Cascade
    {
        "name": "frontier",
        "display_name": "👑 [FREE FRONTIER] Sonnet 5 + GPT-Sol + Kimi K3 Cascade",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities_template
    },
    {
        "name": "auto/pro-coding",
        "display_name": "⚡ [FREE PRO CODING] GPT-5.6 Sol + Sonnet 5 + Kimi K3",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities_template
    },

    # Individual Flagships (100% Free)
    {
        "name": "claude-sonnet-5",
        "display_name": "👑 [FREE] Claude Sonnet 5 (Anthropic Next-Gen)",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities_template
    },
    {
        "name": "gpt-5.6-sol",
        "display_name": "👑 [FREE] GPT-5.6 Sol (Peak Coding ELO 1623)",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities_template
    },
    {
        "name": "kimi-k3",
        "display_name": "👑 [FREE] Kimi K3 (200k Frontier ELO 1674)",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities_template
    },
    {
        "name": "qwen3.8-max-preview",
        "display_name": "👑 [FREE] Qwen 3.8 Max Preview (Alibaba ELO 1671)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities_template
    },
    {
        "name": "glm-5.2",
        "display_name": "👑 [FREE] GLM 5.2 Flagship (Zhipu ELO 1588)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities_template
    },
    {
        "name": "deepseek-v4-pro",
        "display_name": "👑 [FREE] DeepSeek V4 Pro (Frontier Architecture)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities_template
    },
    {
        "name": "deepseek-ai/deepseek-r1",
        "display_name": "👑 [FREE] DeepSeek R1 (Frontier Reasoning)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities_template
    },
    {
        "name": "nvidia/nemotron-3-ultra-550b-a55b",
        "display_name": "👑 [FREE] Nemotron 3 Ultra 550B (NVIDIA MoE Giant)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities_template
    },
    {
        "name": "github/gpt-4o",
        "display_name": "👑 [FREE] GPT-4o (GitHub Developer Free Tier)",
        "max_tokens": 128000,
        "max_output_tokens": 4096,
        "max_completion_tokens": 128000,
        "capabilities": capabilities_template
    },
    {
        "name": "gemini-3.1-pro-preview",
        "display_name": "👑 [FREE] Gemini 3.1 Pro (Google 2M Context)",
        "max_tokens": 1000000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 1000000,
        "capabilities": capabilities_template
    }
]

# Set default model to frontier
settings.setdefault("agent", {})["default_model"] = {
    "enable_thinking": False,
    "provider": "OmniRoute",
    "model": "frontier"
}

openai_compat = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
openai_compat["OmniRoute"] = {
    "api_url": "http://localhost:20128/v1",
    "available_models": zed_free_frontiers
}

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=4, ensure_ascii=False)

print(f"Zed settings updated successfully with {len(zed_free_frontiers)} Free Frontier Flagships!")
