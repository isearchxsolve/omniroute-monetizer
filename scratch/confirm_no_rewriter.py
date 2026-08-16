"""READ-ONLY: confirm no combo-update audit events exist + re-check current weights."""
import json, sys, time, sqlite3
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

# 1. audit_log: any non-login actions at all?
con = sqlite3.connect(r"file:C:\Users\Admin\.omniroute\storage.sqlite?mode=ro", uri=True)
cur = con.cursor()
print("=== distinct audit actions (last 500 rows) ===")
for row in cur.execute("SELECT action, COUNT(*) FROM (SELECT action FROM audit_log ORDER BY rowid DESC LIMIT 500) GROUP BY action ORDER BY 2 DESC"):
    print(f"  {row[0]:40} x{row[1]}")
print("\n=== any combo/model update actions ever ===")
rows = cur.execute("SELECT timestamp, action, actor, target, substr(details,1,120) FROM audit_log WHERE action LIKE '%combo%' OR action LIKE '%model%' OR action LIKE '%update%' OR action LIKE '%put%' ORDER BY rowid DESC LIMIT 20").fetchall()
if not rows:
    print("  (none)")
for r in rows:
    print("  ", r)
con.close()

# 2. current weights, fresh read
s = requests.Session()
for a in range(5):
    try:
        s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45); break
    except Exception:
        time.sleep(10)
rc = s.get(f"{BASE}/api/combos", timeout=45).json()
combos = rc.get("combos", rc if isinstance(rc, list) else [])
print("\n=== CURRENT weights (fresh read) ===")
for c in combos:
    if len(c.get("models", [])) < 2: continue
    print(f"\n{c.get('name')!r} updatedAt={c.get('updatedAt')}")
    for m in c.get("models", []):
        print(f"    w={m.get('weight'):<4} {m.get('model')}")
