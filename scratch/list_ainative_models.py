import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT value FROM key_value WHERE key LIKE 'ainative:%'")
row = c.fetchone()
if row:
    models = json.loads(row[0])
    print(f"Total models on AINative: {len(models)}")
    for m in models:
        mid = m.get('id') if isinstance(m, dict) else m
        print(f"  • {mid}")
conn.close()
