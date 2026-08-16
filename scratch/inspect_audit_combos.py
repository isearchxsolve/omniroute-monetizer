"""READ-ONLY: audit_log around restart + combos referencing the failing models."""
import json
import sqlite3

DB = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

# 1. audit_log schema + rows around 13:05-13:15 UTC (18:35-18:45 local)
cols = [c[1] for c in cur.execute("PRAGMA table_info(audit_log)")]
print("audit_log cols:", cols)
n = cur.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
print("audit_log rows:", n)
rows = cur.execute("SELECT * FROM audit_log ORDER BY rowid DESC LIMIT 40").fetchall()
for row in rows:
    d = dict(zip(cols, row))
    line = " | ".join(f"{k}={str(v)[:90]}" for k, v in d.items() if v is not None)
    print(" ", line[:400])

# 2. combos referencing the failing models
print("\n=== combos table ===")
ccols = [c[1] for c in cur.execute("PRAGMA table_info(combos)")]
print("combos cols:", ccols)
rows = cur.execute("SELECT * FROM combos").fetchall()
failing = ["gpt-5.6-sol", "glm-5.2", "kimi-k3", "llama-3.3-70b"]
for row in rows:
    d = dict(zip(ccols, row))
    blob = json.dumps(d, default=str)
    hits = [f for f in failing if f in blob]
    if hits:
        print(f"\n--- combo id={d.get('id')} name={d.get('name') or d.get('combo_id')} hits={hits}")
        for k, v in d.items():
            sv = str(v)
            if len(sv) > 600:
                sv = sv[:600] + f"...({len(str(v))} chars)"
            print(f"    {k} = {sv}")
con.close()
