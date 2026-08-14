import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all active providers
cursor.execute("SELECT id, provider, name, auth_type FROM provider_connections WHERE is_active = 1")
active_providers = cursor.fetchall()
active_provider_map = {f"{p[1]}:{p[0]}": (p[1], p[2], p[3]) for p in active_providers}
active_provider_ids = {p[0]: (p[1], p[2], p[3]) for p in active_providers}
active_provider_names = set(p[1] for p in active_providers)

print(f"Total Active Providers in DB: {len(active_providers)}")
for p in active_providers:
    print(f"- {p[1]} (Name: {p[2]}, ID: {p[0]}, Auth: {p[3]})")

print("\n" + "="*80)
print("MODELS PER ACTIVE PROVIDER")
print("="*80)

cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels'")
synced_rows = cursor.fetchall()

provider_models = {}
for key, val_str in synced_rows:
    # key is usually provider:connection_id
    try:
        models = json.loads(val_str)
        provider_models[key] = models
    except:
        pass

for p_key, models in provider_models.items():
    print(f"\nProvider Connection: {p_key} ({len(models)} models)")
    for m in models:
        mid = m.get('id') if isinstance(m, dict) else str(m)
        mname = m.get('name') if isinstance(m, dict) else ""
        print(f"   • {mid} | {mname}")

