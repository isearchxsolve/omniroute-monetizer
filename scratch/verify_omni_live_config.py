import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("=" * 80)
print("1. PROVIDER CONNECTION STATUS IN OMNIROUTE DB")
print("=" * 80)
target_providers = ['opencode-zen', 'qoder', 'nvidia', 'github', 'antigravity', 'lmarena', 'opencode']
cursor.execute("SELECT id, provider, name, auth_type, is_active FROM provider_connections")
for row in cursor.fetchall():
    if row[1] in target_providers:
        status = "ACTIVE / ENABLED (1)" if row[4] == 1 else "DISABLED (0)"
        print(f"Provider: {row[1]:<15} | Name: {str(row[2]):<20} | Status: {status}")

print("\n" + "=" * 80)
print("2. COMBO CONFIGURATIONS IN OMNIROUTE DB")
print("=" * 80)
cursor.execute("SELECT id, name, data FROM combos")
for row in cursor.fetchall():
    cdata = json.loads(row[2])
    print(f"\nCombo: {row[1]} (ID: {row[0]})")
    print(f"Description: {cdata.get('description', '')}")
    print(f"Strategy: {cdata.get('strategy', 'auto')}")
    print("Models in Cascade:")
    for m in cdata.get('models', []):
        print(f"  • Model: {m.get('model'):<25} | Provider ID: {m.get('providerId'):<15} | Weight: {m.get('weight', 0)}")

print("\n" + "=" * 80)
print("3. MODEL COMBO MAPPINGS IN OMNIROUTE DB")
print("=" * 80)
cursor.execute("SELECT pattern, combo_id, enabled, description FROM model_combo_mappings")
for row in cursor.fetchall():
    enabled_str = "ENABLED (1)" if row[2] == 1 else "DISABLED (0)"
    print(f"Pattern: {row[0]:<25} -> Combo ID: {row[1]} | {enabled_str} | {row[3]}")

