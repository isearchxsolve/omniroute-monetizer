import sqlite3

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"
conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT key, value FROM key_value WHERE key LIKE 'qoder:%' OR key LIKE 'lmarena:%' OR key LIKE 'codex:%' OR key LIKE 'grok-cli:%' OR key LIKE 'amazon-q:%'")
rows = c.fetchall()
for row in rows:
    print(row)

print("---Combos---")
c.execute("SELECT * FROM combos")
print(c.fetchall())

conn.close()
