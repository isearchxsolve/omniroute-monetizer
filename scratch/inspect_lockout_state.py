"""READ-ONLY: check domain_lockout_state + related lockout tables for openrouter."""
import sqlite3

DB = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()

for t in ["domain_lockout_state", "domain_circuit_breakers", "domain_budgets"]:
    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({t})")]
    print(f"\n=== {t} cols: {cols}")
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"rows: {n}")
        rows = cur.execute(f"SELECT * FROM {t} LIMIT 30").fetchall()
        for row in rows:
            d = dict(zip(cols, row))
            # redact anything key-like
            print(" ", {k: (str(v)[:120]) for k, v in d.items()})
    except Exception as e:
        print("err:", e)

# also check key_value for lockout-ish keys
print("\n=== key_value keys matching lockout/cooldown/unavail ===")
try:
    rows = cur.execute("SELECT key FROM key_value").fetchall()
    for (k,) in rows:
        kl = str(k).lower()
        if any(x in kl for x in ("lockout", "cooldown", "unavail", "openrouter", "rate_limit", "ratelimit")):
            print(" ", k)
except Exception as e:
    print("err:", e)
con.close()
