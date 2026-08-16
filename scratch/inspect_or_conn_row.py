"""READ-ONLY: dump ONLY the connections table row for openrouter."""
import sqlite3

DB = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("all tables:", tables)

# find table that has provider + isActive columns
for t in tables:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
    low = [c.lower() for c in cols]
    if "provider" in low and ("isactive" in low or "is_active" in low):
        print(f"\n>>> connection table = {t}")
        print("cols:", cols)
        rows = cur.execute(f"SELECT * FROM {t} WHERE lower(provider)='openrouter'").fetchall()
        for row in rows:
            print("\n--- openrouter row ---")
            for c, v in zip(cols, row):
                sv = str(v)
                cl = c.lower()
                if any(k in cl for k in ("key", "token", "secret", "password")):
                    sv = (sv[:12] + "...REDACTED") if v else "(null)"
                elif len(sv) > 400:
                    sv = sv[:400] + f"...({len(str(v))} chars)"
                print(f"  {c} = {sv}")
con.close()
