import sqlite3

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT key FROM key_value")
rows = c.fetchall()
print(f"Total keys in key_value: {len(rows)}")
for r in rows:
    print(f"  - {r[0]}")

conn.close()
