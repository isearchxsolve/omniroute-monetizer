"""Inspect storage.sqlite provider_connections schema + encrypted key format."""
import sqlite3

DB = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()
cols = cur.execute("PRAGMA table_info(provider_connections)").fetchall()
print("cols:", [c[1] for c in cols])
rows = cur.execute(
    "SELECT provider, auth_type, is_active, test_status, substr(api_key, 1, 30) FROM provider_connections WHERE is_active = 1"
).fetchall()
print(f"\nactive rows: {len(rows)}")
for r in rows:
    print(f"  {r[0]} [{r[1]}] status={r[3]} key_prefix={r[4]!r}")
con.close()
