import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all active providers
cursor.execute("SELECT id, provider, name, auth_type, is_active FROM provider_connections WHERE is_active = 1")
active_providers = cursor.fetchall()
active_provider_map = {f"{p[1]}:{p[0]}": (p[1], p[2], p[3]) for p in active_providers}

cursor.execute("SELECT key, value FROM key_value WHERE namespace = 'syncedAvailableModels'")
synced_rows = cursor.fetchall()

provider_models = {}
for key, val_str in synced_rows:
    try:
        models = json.loads(val_str)
        provider_models[key] = models
    except:
        pass

print("ACTIVE PROVIDER SUMMARY & MODEL CATALOG:")
print("=" * 80)
for p in active_providers:
    pid = p[0]
    p_name = p[1]
    display_name = p[2]
    auth = p[3]
    
    # find matching synced models
    matched_models = []
    for k, v in provider_models.items():
        if pid in k or k.startswith(f"{p_name}:"):
            matched_models = v
            break
            
    print(f"\n[PROVIDER] {p_name.upper()} (Name: {display_name} | ID: {pid} | Auth: {auth})")
    print(f"Total Models: {len(matched_models)}")
    if matched_models:
        for m in matched_models:
            mid = m.get('id') if isinstance(m, dict) else str(m)
            mname = m.get('name') if isinstance(m, dict) else ""
            print(f"  • {mid} ({mname})")
    else:
        print("  • (Uses default / standard models for this provider family)")
