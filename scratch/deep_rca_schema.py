import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== TABLE SCHEMAS ===")
for t in ["provider_connections", "combos", "model_combo_mappings"]:
    c.execute(f"PRAGMA table_info({t})")
    print(f"Table {t}:")
    for col in c.fetchall():
        print(f"   {col[1]} ({col[2]})")

print("\n=== ACTIVE PROVIDER CONNECTIONS ===")
c.execute("SELECT id, provider, name, auth_type, is_active FROM provider_connections WHERE is_active = 1")
for row in c.fetchall():
    print(f"ID: {row[0][:8]} | Provider: {row[1]:<15} | Name: {str(row[2]):<25} | Auth: {row[3]}")

conn.close()
