import sqlite3
import json

db_path = r"C:\Users\Admin\.omutu\storage.sqlite"
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get existing combos
c.execute("SELECT id, name, data FROM combos")
rows = c.fetchall()

combo_updates = {
    'Frontier Max': [
        "lmarena/claude-sonnet-5",
        "codex/gpt-5.6-sol", 
        "qoder/qwen3.8-max-preview",
        "grok-cli/grok-4.5",
        "lmarena/deepseek-v4-pro-thinking"
    ],
    'auto/free-chat': [
        "qoder/kimi-k3",
        "lmarena/claude-sonnet-5",
        "codex/gpt-5.6-sol",
        "lmarena/gpt-5.2-high",
        "amazon-q/amazon-q"
    ],
    'auto/pro-coding': [
        "lmarena/claude-sonnet-5",
        "codex/gpt-5.6-sol",
        "qoder/kimi-k3",
        "qoder/qwen3.7-max"
    ],
    'auto/asian-flagships': [
        "qoder/kimi-k3",
        "qoder/qwen3.8-max-preview",
        "lmarena/deepseek-v4-pro-thinking",
        "qoder/glm-5.2"
    ]
}

for r in rows:
    combo_id = r[0]
    combo_name = r[1]
    combo_desc = r[2]
    
    if combo_name in combo_updates:
        try:
            desc_dict = json.loads(combo_desc)
            existing_models = desc_dict.get('models', [])
            
            # Add new models at priority 1, shift others down
            new_model_names = combo_updates[combo_name]
            
            updated_models = []
            priority = 1
            weight = 100
            
            # Add the requested user models first
            for mn in new_model_names:
                updated_models.append({
                    "name": mn,
                    "weight": weight,
                    "priority": priority
                })
                priority += 1
                weight = max(10, weight - 5)
                
            # Add the rest that aren't duplicates
            for em in existing_models:
                if em["name"] not in new_model_names:
                    updated_models.append({
                        "name": em["name"],
                        "weight": weight,
                        "priority": priority
                    })
                    priority += 1
                    weight = max(10, weight - 5)
            
            desc_dict["models"] = updated_models
            
            # Update DB
            c.execute("UPDATE combos SET data = ? WHERE id = ?", (json.dumps(desc_dict), combo_id))
            print(f"Updated combo: {combo_name}")
        except Exception as e:
            print(f"Failed to update {combo_name}: {e}")

conn.commit()

# Ensure all these providers are set to active
providers_to_activate = ["lmarena", "qoder", "codex", "grok-cli", "amazon-q"]
for p in providers_to_activate:
    c.execute("UPDATE provider_connections SET is_active = 1 WHERE provider = ?", (p,))
conn.commit()

conn.close()
print("Database updated successfully.")
