import sqlite3
import json
from pathlib import Path
import os

print("=== CONSTRUCTING MASTER CASCADE WITH ALL 12 VERIFIED PROVIDERS ===")

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Set all 12 working providers active
working_providers = [
    "ainative", "zai-web", "cerebras", "alibaba", "agnes", 
    "aion", "cloudflare-ai", "cohere", "antigravity", "kimi-coding", "kilocode", "cline"
]

for p in working_providers:
    c.execute("UPDATE provider_connections SET is_active = 1 WHERE provider = ?", (p,))

# 1. Frontier Max (Claude Sonnet 4.5/4.6, Opus 4, DeepSeek R1, Qwen 3.7 Max, GLM 5.2)
frontier_models = [
    {"name": "ainative/claude-sonnet-4-5", "weight": 100, "priority": 1},
    {"name": "ainative/claude-opus-4", "weight": 95, "priority": 2},
    {"name": "alibaba/qwen3.7-max", "weight": 90, "priority": 3},
    {"name": "ainative/deepseek-r1", "weight": 85, "priority": 4},
    {"name": "zai-web/glm-5.2", "weight": 80, "priority": 5},
    {"name": "cerebras/gemma-4-31b", "weight": 75, "priority": 6},
    {"name": "cerebras/gpt-oss-120b", "weight": 70, "priority": 7}
]

# 2. Pro Coding (Claude Sonnet, Qwen 3.7 Plus, GLM 5.2, Agnes 2.0 Flash)
pro_coding_models = [
    {"name": "ainative/claude-sonnet-4-5", "weight": 100, "priority": 1},
    {"name": "alibaba/qwen3.7-plus", "weight": 95, "priority": 2},
    {"name": "zai-web/glm-5.2", "weight": 90, "priority": 3},
    {"name": "agnes/agnes-2.0-flash", "weight": 85, "priority": 4},
    {"name": "cerebras/zai-glm-4.7", "weight": 80, "priority": 5}
]

# 3. Free Chat / Fast Router (Aya Expanse, Cloudflare Llama 3.2, Agnes 1.5 Flash, Aion 2.0)
free_chat_models = [
    {"name": "cohere/c4ai-aya-expanse-32b", "weight": 100, "priority": 1},
    {"name": "cloudflare-ai/@cf/meta/llama-3.2-3b-instruct", "weight": 95, "priority": 2},
    {"name": "agnes/agnes-1.5-flash", "weight": 90, "priority": 3},
    {"name": "aion/aion-labs/aion-2.0", "weight": 85, "priority": 4}
]

# 4. Asian Flagships (Qwen 3.7 Max + GLM 5.2 + Kimi)
asian_flagships = [
    {"name": "alibaba/qwen3.7-max", "weight": 100, "priority": 1},
    {"name": "alibaba/qwen3.7-plus", "weight": 95, "priority": 2},
    {"name": "zai-web/glm-5.2", "weight": 90, "priority": 3},
    {"name": "kimi-coding/kimi-coding-default", "weight": 85, "priority": 4}
]

combos = [
    ("4a4de0d2-fba6-45d4-a74d-5f06b196c300", "Frontier Max", frontier_models),
    ("66e7fa63-0bd4-4d46-b06e-3669d407459c", "auto/pro-coding", pro_coding_models),
    ("7e521395-b148-4755-903a-4d3152d44019", "auto/free-chat", free_chat_models),
    ("b12c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e", "auto/asian-flagships", asian_flagships)
]

for cid, name, models in combos:
    data = {
        "models": models,
        "strategy": "priority",
        "description": f"Verified Live Fleet Cascade for {name}",
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

mappings = [
    ("frontier", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 100),
    ("auto/pro-coding", "66e7fa63-0bd4-4d46-b06e-3669d407459c", 100),
    ("auto/free-chat", "7e521395-b148-4755-903a-4d3152d44019", 100),
    ("auto/asian-flagships", "b12c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e", 100),
    ("claude-sonnet-4.6", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 90),
    ("claude-sonnet-4.5", "4a4de0d2-fba6-45d4-a74d-5f06b196c300", 90),
    ("qwen3.7-max", "b12c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e", 90)
]

for pattern, combo_id, prio in mappings:
    c.execute("DELETE FROM model_combo_mappings WHERE pattern = ?", (pattern,))
    c.execute("""
        INSERT INTO model_combo_mappings (id, pattern, combo_id, priority, enabled, description, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, 'Auto-mapped live fleet cascade', datetime('now'), datetime('now'))
    """, (f"map-{pattern.replace('/', '-')}", pattern, combo_id, prio))

conn.commit()
conn.close()

# 2. Update Zed Settings
zed_path = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "Zed" / "settings.json"
zed_path.parent.mkdir(parents=True, exist_ok=True)

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
        "display_name": "👑 [FREE FRONTIER] Claude Sonnet + Claude Opus + Qwen 3.7 Max + GLM 5.2",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "auto/pro-coding",
        "display_name": "⚡ [PRO CODING] Claude Sonnet + Qwen 3.7 Plus + GLM 5.2 + Agnes 2.0",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "auto/asian-flagships",
        "display_name": "🐉 [ASIAN FRONTIERS] Qwen 3.7 Max + GLM 5.2 + Kimi Coding",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "auto/free-chat",
        "display_name": "🆓 [FREE FAST] Cohere Aya + Cloudflare Llama 3.2 + Agnes Flash",
        "max_tokens": 128000,
        "max_output_tokens": 8192,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    # Direct Verified Endpoints
    {
        "name": "ainative/claude-sonnet-4-5",
        "display_name": "👑 [LIVE] Claude Sonnet 4.5 / 4.6 (Anthropic)",
        "max_tokens": 200000,
        "max_output_tokens": 32000,
        "max_completion_tokens": 200000,
        "capabilities": capabilities
    },
    {
        "name": "alibaba/qwen3.7-max",
        "display_name": "👑 [LIVE] Qwen 3.7 Max (Alibaba Cloud Model Studio)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "alibaba/qwen3.7-plus",
        "display_name": "⚡ [LIVE] Qwen 3.7 Plus (Alibaba Cloud Model Studio — 3.1s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "zai-web/glm-5.2",
        "display_name": "👑 [LIVE] GLM 5.2 Flagship (Z.ai Web Free — 2.5s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "cerebras/gemma-4-31b",
        "display_name": "⚡ [LIVE] Gemma 4 31B (Cerebras Ultra-Fast)",
        "max_tokens": 128000,
        "max_output_tokens": 16384,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "agnes/agnes-2.0-flash",
        "display_name": "⚡ [LIVE] Agnes 2.0 Flash (Agnes AI — 2.6s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 8192,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    },
    {
        "name": "cohere/c4ai-aya-expanse-32b",
        "display_name": "⚡ [LIVE] Cohere Aya Expanse 32B (2.8s TTFT)",
        "max_tokens": 128000,
        "max_output_tokens": 8192,
        "max_completion_tokens": 128000,
        "capabilities": capabilities
    }
]

settings = {}
if zed_path.exists():
    try:
        settings = json.loads(zed_path.read_text(encoding="utf-8"))
    except:
        settings = {}

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
print(f"[+] Successfully wrote complete 12-provider live config to Zed: {zed_path}")
