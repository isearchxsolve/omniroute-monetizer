import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== 1. ACTIVE PROVIDER CONNECTIONS ===")
cursor.execute("SELECT id, provider, name, auth_type, is_active FROM provider_connections WHERE is_active = 1")
active_providers = cursor.fetchall()
for p in active_providers:
    print(f"ID: {p[0]} | Provider: {p[1]} | Name: {p[2]} | Auth: {p[3]}")

print("\n=== 2. SYNCED AVAILABLE MODELS BY PROVIDER ===")
cursor.execute("SELECT key, sub_key, value FROM key_value WHERE key = 'syncedAvailableModels' OR key = 'models'")
synced = cursor.fetchall()
provider_models = {}
for s in synced:
    try:
        models_data = json.loads(s[2])
        provider_models[s[1]] = models_data
        print(f"Provider Key: {s[1]} -> {len(models_data)} models")
    except Exception as e:
        print(f"Error parsing models for {s[1]}: {e}")

print("\n=== 3. ALL COMBOS ===")
cursor.execute("SELECT id, name, data FROM combos")
combos = cursor.fetchall()
for c in combos:
    data = json.loads(c[2])
    print(f"Combo: {c[1]} ({c[0]})")
    for m in data.get('models', []):
        print(f"  - {m.get('model')} (provider: {m.get('providerId')})")

print("\n=== 4. MODEL COMBO MAPPINGS ===")
cursor.execute("SELECT pattern, combo_id, description, enabled FROM model_combo_mappings")
mappings = cursor.fetchall()
for m in mappings:
    print(f"Pattern: {m[0]} -> Combo ID: {m[1]} (enabled: {m[3]}) - {m[2]}")

