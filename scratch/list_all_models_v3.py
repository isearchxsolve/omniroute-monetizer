import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=== ALL NAMESPACES IN KEY_VALUE ===")
cursor.execute("SELECT DISTINCT namespace FROM key_value")
for n in cursor.fetchall():
    print(n[0])

print("\n=== SYNCED AVAILABLE MODELS IN KEY_VALUE ===")
cursor.execute("SELECT namespace, key, value FROM key_value WHERE namespace = 'syncedAvailableModels'")
rows = cursor.fetchall()
all_models_by_provider = {}
for r in rows:
    try:
        data = json.loads(r[2])
        provider_name = r[1]
        all_models_by_provider[provider_name] = data
        print(f"\nProvider: {provider_name} ({len(data)} models)")
        for m in data:
            if isinstance(m, dict):
                print(f"  - {m.get('id')} ({m.get('name')})")
            else:
                print(f"  - {m}")
    except Exception as e:
        print(f"Error parsing {r[1]}: {e}")

print("\n=== MODEL ALIASES IN KEY_VALUE ===")
cursor.execute("SELECT namespace, key, value FROM key_value WHERE namespace = 'modelAliases'")
for r in cursor.fetchall():
    print(f"{r[1]} -> {r[2]}")

print("\n=== DISCOVERY RESULTS TABLE ===")
try:
    cursor.execute("SELECT * FROM discovery_results")
    for r in cursor.fetchall():
        print(r)
except Exception as e:
    print(e)
