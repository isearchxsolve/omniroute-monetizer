import sqlite3
import json
import uuid
import datetime

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== 1. DISABLING BROKEN / DEAD PROVIDERS ===")
dead_providers = ["opencode-zen", "opencode", "antigravity", "openrouter", "trae", "windsurf", "cline"]
for p in dead_providers:
    c.execute("UPDATE provider_connections SET is_active = 0 WHERE provider = ?", (p,))
    print(f"Disabled provider: {p}")

print("\n=== 2. ACTIVE HEALTHY PROVIDERS REMAINING ===")
c.execute("SELECT provider, name, auth_type FROM provider_connections WHERE is_active = 1")
for row in c.fetchall():
    print(f"  • {row[0]:<15} | Name: {str(row[1]):<20} | Auth: {row[2]}")

print("\n=== 3. REBUILDING CLEAN FRONTIER & PRO CASCADES ===")
# Define clean combos without any opencode-zen or dead upstreams
frontier_models = [
    {"name": "qoder/kimi-k3", "weight": 100, "priority": 1},
    {"name": "qoder/qwen3.8-max-preview", "weight": 95, "priority": 2},
    {"name": "nvidia/z-ai/glm-5.2", "weight": 90, "priority": 3},
    {"name": "qoder/deepseek-v4-pro", "weight": 85, "priority": 4},
    {"name": "nvidia/deepseek-ai/deepseek-r1", "weight": 80, "priority": 5},
    {"name": "nvidia/nvidia/nemotron-3-ultra-550b-a55b", "weight": 75, "priority": 6},
    {"name": "github/gpt-4o", "weight": 70, "priority": 7},
]

pro_coding_models = [
    {"name": "qoder/kimi-k3", "weight": 100, "priority": 1},
    {"name": "qoder/qwen3.8-max-preview", "weight": 95, "priority": 2},
    {"name": "nvidia/z-ai/glm-5.2", "weight": 90, "priority": 3},
    {"name": "qoder/deepseek-v4-pro", "weight": 85, "priority": 4},
    {"name": "github/gpt-4o", "weight": 80, "priority": 5},
    {"name": "github/gpt-4o-mini", "weight": 70, "priority": 6},
]

free_chat_models = [
    {"name": "github/gpt-4o-mini", "weight": 100, "priority": 1},
    {"name": "nvidia/meta/llama-3.3-70b-instruct", "weight": 90, "priority": 2},
    {"name": "qoder/deepseek-v4-flash", "weight": 85, "priority": 3},
]

combos_to_update = [
    ("4a4de0d2-fba6-45d4-a74d-5f06b196c300", "Frontier Max", frontier_models),
    ("66e7fa63-0bd4-4d46-b06e-3669d407459c", "auto/pro-coding", pro_coding_models),
    ("7e521395-b148-4755-903a-4d3152d44019", "auto/free-chat", free_chat_models),
]

for cid, name, mlist in combos_to_update:
    combo_data = {
        "models": mlist,
        "strategy": "priority",
        "description": f"Optimized zero-cost cascade for {name} with dead-route suppression",
        "retries": 1,
        "retry_delay": 500,
        "timeout": 15000
    }
    c.execute("""
        INSERT INTO combos (id, name, data, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
        ON CONFLICT(id) DO UPDATE SET 
            name = excluded.name,
            data = excluded.data,
            updated_at = datetime('now')
    """, (cid, name, json.dumps(combo_data)))
    print(f"Updated combo: {name} ({cid})")

conn.commit()
conn.close()
print("\n[+] Database repaired successfully!")
