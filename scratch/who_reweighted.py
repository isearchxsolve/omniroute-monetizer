"""READ-ONLY: figure out what re-weighted combos between #57 (19:35) and now."""
import json, sys, time, sqlite3
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

# 1. current combo weights right now
s = requests.Session()
for a in range(5):
    try:
        s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45); break
    except Exception as e:
        time.sleep(10)
rc = s.get(f"{BASE}/api/combos", timeout=45).json()
combos = rc.get("combos", rc if isinstance(rc, list) else [])
print("=== CURRENT combo weights (now) ===")
for c in combos:
    if len(c.get("models", [])) < 2: continue
    print(f"\n{c.get('name')!r} updatedAt={c.get('updatedAt')}")
    for m in c.get("models", []):
        print(f"    w={m.get('weight'):<4} {m.get('model')}")

# 2. compare with the #57 backup
print("\n=== #57 BACKUP weights (state/combos_backup_20260816_193115.json) ===")
try:
    bak = json.load(open(r"d:\omniroute-monetizer\state\combos_backup_20260816_193115.json", encoding="utf-8"))
    for c in bak:
        if len(c.get("models", [])) < 2: continue
        print(f"\n{c.get('name')!r} updatedAt={c.get('updatedAt')}")
        for m in c.get("models", []):
            print(f"    w={m.get('weight'):<4} {m.get('model')}")
except Exception as e:
    print("backup read failed:", e)

# 3. audit_log for combo updates
print("\n=== audit_log recent (combo-ish) ===")
con = sqlite3.connect(r"file:C:\Users\Admin\.omniroute\storage.sqlite?mode=ro", uri=True)
cur = con.cursor()
cols = [c[1] for c in cur.execute("PRAGMA table_info(audit_log)")]
rows = cur.execute("SELECT * FROM audit_log ORDER BY rowid DESC LIMIT 30").fetchall()
for row in rows:
    d = dict(zip(cols, row))
    line = " | ".join(f"{k}={str(v)[:70]}" for k, v in d.items() if v is not None)
    print("  ", line[:300])
con.close()
