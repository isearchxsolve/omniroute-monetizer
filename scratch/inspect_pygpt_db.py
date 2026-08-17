"""Inspect PyGPT db.sqlite to find what happened during the failed agent runs."""
import sqlite3
import json

DB = r"C:\Users\Admin\.config\pygpt-net\db.sqlite"

c = sqlite3.connect(DB)
cur = c.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("TABLES:", tables)

# Look for ctx / item tables
for t in tables:
    cur.execute(f"PRAGMA table_info({t})")
    cols = [r[1] for r in cur.fetchall()]
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    n = cur.fetchone()[0]
    print(f"\n== {t} ({n} rows) cols={cols}")

c.close()
