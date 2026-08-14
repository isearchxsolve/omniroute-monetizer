import requests
import json
import sqlite3

# Let's inspect the active sessions / tokens in SQLite
db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT key, value FROM key_value WHERE key LIKE '%session%' OR key LIKE '%token%' OR key LIKE '%jwt%'")
rows = c.fetchall()
print("Found tokens/sessions in key_value:")
for r in rows:
    print(f"  Key: {r[0]} | Value: {r[1][:50]}")
conn.close()
