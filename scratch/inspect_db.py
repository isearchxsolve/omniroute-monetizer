import sqlite3
import json

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# See if there's a table named 'combos' or similar
for t in tables:
    if 'combo' in t[0].lower() or 'config' in t[0].lower() or 'setting' in t[0].lower() or 'user' in t[0].lower():
        print(f"\nSchema for {t[0]}:")
        cursor.execute(f"PRAGMA table_info({t[0]})")
        print(cursor.fetchall())
        
        # Select first row
        try:
            cursor.execute(f"SELECT * FROM {t[0]} LIMIT 1")
            row = cursor.fetchone()
            print(f"First row of {t[0]}: {row}")
        except Exception as e:
            print(e)
