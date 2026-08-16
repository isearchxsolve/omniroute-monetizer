import sqlite3, os, sys

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
uri = "file:" + db.replace("\\", "/") + "?mode=ro"
con = sqlite3.connect(uri, uri=True)
cur = con.cursor()

# list tables
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)

# find table likely holding connections
for t in tables:
    if "connection" in t.lower() or "provider" in t.lower():
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"\n== {t} ({n} rows) cols: {cols}")

con.close()
