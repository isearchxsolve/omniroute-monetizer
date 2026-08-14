import sqlite3
import json
from pathlib import Path
import os

print("=== INTEGRATING CLAUDE SONNET, OPUS & FULL FLAGSHIPS ===")

# 1. Update SQLite Combos
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Ensure ainative, zai-web, github, cerebras, nvidia, cloudflare-ai are active
c.execute("UPDATE provider_connections SET is_active = 1 WHERE provider IN ('ainative', 'zai-web', 'github', 'cerebras', 'nvidia', 'cloudflare-ai', 'cohere')")

# Frontier Max Cascade (Frontier Flagships with Claude Sonnet & Opus at the helm)
frontier_models = [
    {"name": "ainative/claude-sonnet-4-5", "weight": 100, "priority": 1},
    {"name": "ainative/claude-opus-4", "weight": 95, "priority": 2},
    {"name": "ainative/deepseek-r1", "weight": 90, "priority": 3},
    {"name": "zai-web/glm-5.2", "weight": 85, "priority": 4},
    {"name": "github/gpt-4o", "weight": 80, "priority": 5},
    {"name": "cerebras/zai-glm-4.7", "weight": 75, "priority": 6},
    {"name": "nvidia/nvidia/nemotron-3-ultra-550b-a55b", "weight": 70, "priority": 7},
]

# Pro Coding Cascade (Claude Sonnet + GLM 5.2 + GPT-4o + Cerebras)
pro_coding_models = [
    {"name": "ainative/claude-sonnet-4-5", "weight": 100, "priority": 1},
    {"name": "zai-web/glm-5.2", "weight": 95, "priority": 2},
    {"name": "github/gpt-4o", "weight": 90, "priority": 3},
    {"name": "cerebras/zai-glm-4.7", "weight": 85, "priority": 4},
    {"name": "github/gpt-4o-mini", "weight": 80, "priority": 5},
]

# Free Fast Chat
free_chat_models = [
    {"name": "github/gpt-4o-mini", "weight": 100, "priority": 1},
    {"name": "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct", "weight": 90, "priority": 2},
    {"name": "cohere/c4ai-aya-expanse-32b", "weight": 85, "priority": 3},
]

combos = [
    ("4a4de0d2-fba6-45d4-a74d-5f06b196c300", "Frontier Max", frontier_models),
    ("66e7fa63-0bd4-4d46-b06e-3669d407459c", "auto/pro-coding", pro_coding_models),
    ("7e521395-b148-4755-903a-4d3152d44019", "auto/free-chat", free_chat_models),
]

for cid, name, models in combos:
    data = {
        "models": models,
        "strategy": "priority",
        "description": f"Verified Frontier Flagship Cascade for {name}",
        "retries": 2,
        "retry_delay": 300,
        "timeout": 15000
    }
    c.execute("""
        INSERT INTO combos (id, name, data, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
        ON CONFLICT(id) DO UPDATE SET 
            name = excluded.name,
            data = excluded.data,
            updated_at = datetime('now')
    """, (cid, name, json.dumps(data)))
    print(f"Updated combo: {name}")

# Map aliases
mappings = [
    ("frontier", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 100),
    ("auto/pro-coding", "66e7fa63-0bd4-4d46-b06e-3669d407459c", 100),
    ("auto/free-chat", "7e521395-b148-4755-903a-4d3152d44019", 100),
    ("auto/pro-reasoning", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 90),
    ("claude-sonnet-4.6", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 90),
    ("claude-sonnet-4.5", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 90),
]

for pattern, combo_id, prio in mappings:
    c.execute("DELETE FROM model_combo_mappings WHERE pattern = ?", (pattern,))
    c.execute("""
        INSERT INTO model_combo_mappings (id, pattern, combo_id, priority, enabled, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, 'Auto-mapped flagship cascade', datetime('now'), datetime('now'))
    """, (f"map-{pattern.replace('/', '-')}", pattern, combo_id, prio))
    print(f"Mapped alias: {pattern} -> {combo_id}")

conn.commit()
conn.close()

# 2. Update Zed Settings
zed_path = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Zed" / "settings.json"
zed_path.parent.mkdir(parents=True, exist_ok=True)

settings = {}
if zed_path.exists():
    try:
        settings = json.loads(zed_path.read_text(encoding="utf-8"))
    except:
        settings = {}

capabilities = {
    "tools": True,
    "images": True,
    "parallel_tool_calls": False,
    "prompt_cache_key": False,
    "chat_completions": True,
    "interleaved_reasoning": False,
    "max_tokens_parameter": False
}

available_models = [
    # Top Cascades
    {
        "name": "frontier",
        "display_name": "👑 [FREE FRONTIER] Claude Sonnet + Claude Opus + DeepSeek R1 + GLM 5.2",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "auto/pro-coding",
        "display_name": "⚡ [FREE PRO CODING] Claude Sonnet + GLM 5.2 + GPT-4o + Cerebras",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "auto/free-chat",
        "display_name": "🆓 [FREE] Fast Free Router (GPT-4o Mini + Llama 3.2 + Cohere)",
        "max_tokens": 128000,
        "max_output_tokens": 8192,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    # Direct Verified Flagships
    {
        "name": "ainative/claude-sonnet-4-5",
        "display_name": "👑 [LIVE] Claude Sonnet 4.5 / 4.6 (Anthropic Frontier)",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "ainative/claude-opus-4",
        "display_name": "👑 [LIVE] Claude Opus 4 (Anthropic Ultra-Reasoning)",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "ainative/deepseek-r1",
        "display_name": "👑 [LIVE] DeepSeek R1 (Frontier Reasoning)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "zai-web/glm-5.2",
        "display_name": "👑 [LIVE] GLM 5.2 Flagship (Zhipu ELO 1588 — 2.4s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "github/gpt-4o",
        "display_name": "👑 [LIVE] GPT-4o (GitHub Free Tier — 3.8s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 4096,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "cerebras/zai-glm-4.7",
        "display_name": "⚡ [LIVE] GLM-4.7 (Cerebras Ultra-Fast — 2.7s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "github/gpt-4o-mini",
        "display_name": "⚡ [LIVE] GPT-4o Mini (GitHub Free Tier — 3.4s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 4096,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    }
]

settings.setdefault("agent", {})["default_model"] = {
    "enable_thinking": False,
    "provider": "OmniRoute",
    "model": "frontier"
}

lm = settings.setdefault("language_models", {}).setdefault("openai_compatible", {})
lm["OmniRoute"] = {
    "api_url": "http://localhost:20128/v1",
    "available_models": available_models
}

zed_path.write_text(json.dumps(settings, indent=4, ensure_ascii=False), encoding="utf-8")
print(f"[+] Zed configured with Sonnet & Flagships at: {zed_path}")
