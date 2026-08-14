import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Schema of key_value:")
print(cursor.execute("PRAGMA table_info(key_value)").fetchall())

cursor.execute("SELECT * FROM key_value LIMIT 5")
print("\nSample rows of key_value:")
for r in cursor.fetchall():
    print(r[0], r[1] if len(r)>1 else "", (str(r[2])[:100] if len(r)>2 else ""))

print("\n--- Model related entries in key_value ---")
cursor.execute("SELECT * FROM key_value WHERE key LIKE '%model%' OR key LIKE '%sync%'")
rows = cursor.fetchall()
for r in rows:
    val_str = str(r[-1])
    print(f"Row: {r[:-1]} -> value len: {len(val_str)}")
    if len(val_str) > 0 and (val_str.startswith('[') or val_str.startswith('{')):
        try:
            parsed = json.loads(val_str)
            if isinstance(parsed, list):
                print(f"  Count: {len(parsed)} items. Sample: {parsed[:3]}")
            elif isinstance(parsed, dict):
                print(f"  Keys: {list(parsed.keys())[:5]}")
        except:
            pass

print("\n--- Model Intelligence table ---")
cursor.execute("SELECT DISTINCT model, category, score, elo_raw FROM model_intelligence ORDER BY elo_raw DESC LIMIT 30")
for r in cursor.fetchall():
    print(r)

print("\n--- Model Capabilities table ---")
try:
    cursor.execute("SELECT * FROM model_capabilities LIMIT 20")
    for r in cursor.fetchall():
        print(r)
except Exception as e:
    print(e)
