import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT key, value FROM key_value WHERE key LIKE 'syncedAvailableModels%'")
for key, val in c.fetchall():
    try:
        data = json.loads(val)
        if isinstance(data, list):
            print(f"Key: {key:<40} | Models: {len(data)}")
            print(f"   Sample: {data[:5]}")
        elif isinstance(data, dict):
            print(f"Key: {key:<40} | Dict keys: {list(data.keys())[:5]}")
    except Exception as e:
        print(f"Key: {key:<40} | Error: {e}")

conn.close()
