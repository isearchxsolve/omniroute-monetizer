"""Inspect the format of the existing chat.lm.secret value."""
import sqlite3

DB = r"C:\Users\Admin\AppData\Roaming\Code\User\globalStorage\state.vscdb"

con = sqlite3.connect(DB)
cur = con.cursor()
row = cur.execute("SELECT value FROM ItemTable WHERE key = 'secret://chat.lm.secret.-2d4b2ee5'").fetchone()
con.close()

v = row[0]
print("type:", type(v))
if isinstance(v, bytes):
    print("len:", len(v))
    print("first 64 bytes hex:", v[:64].hex())
    print("first 64 bytes repr:", repr(v[:64]))
else:
    print("len:", len(v))
    print("first 200 chars:", v[:200])
