import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== DEEP PROVIDER INSPECTION ===")
c.execute("SELECT id, provider, name, auth_type, is_active, json_extract(data, '$.models') FROM provider_connections WHERE is_active = 1")
rows = c.fetchall()
for row in rows:
    pid, provider, name, auth_type, is_active, models_json = row
    models = json.loads(models_json) if models_json else []
    print(f"[{provider}] ID: {pid[:8]} | Name: {name} | Auth: {auth_type} | Models Count: {len(models)}")
    if models:
        print(f"   First 5 models: {models[:5]}")

print("\n=== COMBOS INSPECTION ===")
c.execute("SELECT id, name, data FROM combos")
for row in c.fetchall():
    cid, name, data = row
    d = json.loads(data) if data else {}
    models = d.get('models', [])
    print(f"Combo: {name} ({cid[:8]}) | Strategy: {d.get('strategy')} | Models ({len(models)}):")
    for m in models:
        print(f"   - {m.get('name')} (weight: {m.get('weight')}, priority: {m.get('priority')})")

print("\n=== MODEL COMBO MAPPINGS ===")
c.execute("SELECT model, combo_id FROM model_combo_mappings")
for row in c.fetchall():
    print(f"   {row[0]:<30} -> {row[1]}")

conn.close()
