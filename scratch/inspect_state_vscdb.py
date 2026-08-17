"""Inspect VS Code state.vscdb for chat.lm.secret entries."""
import sqlite3

DB = r"C:\Users\Admin\AppData\Roaming\Code\User\globalStorage\state.vscdb"

con = sqlite3.connect(DB)
cur = con.cursor()
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("tables:", tables)
for (t,) in tables:
    rows = cur.execute(f"SELECT key, length(value) FROM {t} WHERE key LIKE '%chat.lm.secret%'").fetchall()
    print(f"{t}: {len(rows)} secret rows")
    for k, ln in rows:
        print(f"  {k} (len={ln})")
con.close()
