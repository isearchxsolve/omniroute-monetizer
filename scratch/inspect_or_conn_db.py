"""READ-ONLY inspection of the openrouter connection's persisted state in storage.sqlite."""
import json
import sqlite3

DB = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

# list tables
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)

# find the connections table
conn_table = None
for t in tables:
    if "connection" in t.lower() or "provider" in t.lower():
        cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
        print(f"\n{t}: {cols}")
        if conn_table is None and any("apiKey" in c or "api_key" in c or "provider" in c.lower() for c in cols):
            conn_table = t

# dump the openrouter row fully
for t in tables:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
    if "provider" in [c.lower() for c in cols] and "id" in [c.lower() for c in cols]:
        try:
            rows = cur.execute(f"SELECT * FROM {t} WHERE lower(provider)='openrouter'").fetchall()
        except Exception:
            continue
        if rows:
            print(f"\n=== openrouter rows in {t} ===")
            for row in rows:
                for c, v in zip(cols, row):
                    sv = str(v)
                    if len(sv) > 300:
                        sv = sv[:300] + f"...({len(str(v))} chars)"
                    # redact key material
                    if "key" in c.lower() or "token" in c.lower() or "secret" in c.lower():
                        sv = sv[:10] + "...REDACTED" if v else "(null)"
                    print(f"  {c} = {sv}")
con.close()
