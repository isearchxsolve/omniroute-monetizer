import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("\n--- combos ---")
try:
    cursor.execute("SELECT id, name, data FROM combos")
    rows = cursor.fetchall()
    for r in rows:
        data = json.loads(r[2])
        models = data.get('models', [])
        print(f"Combo: {r[1]} ({r[0]}) -> {len(models)} models")
except Exception as e:
    print(e)
