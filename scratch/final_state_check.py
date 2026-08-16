"""Final state check: latest log tail + openrouter connection status + any ongoing errors."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)

# 1. openrouter connection current status via API
OR_ID = "49aa144d-9005-4968-a6cd-a36e8a2e947f"
r = s.get(f"{BASE}/api/providers/{OR_ID}", timeout=15).json()
c = r.get("connection", {})
print("openrouter conn:", json.dumps({
    "isActive": c.get("isActive"),
    "testStatus": c.get("testStatus"),
    "backoffLevel": c.get("backoffLevel"),
    "lastTested": c.get("lastTested"),
    "rateLimitedUntil": c.get("rateLimitedUntil"),
}, indent=2))

# 2. latest log tail — any errors in last 60 lines?
LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

print(f"\n=== last 40 log lines (errors/warns flagged) ===")
err_count = 0
for l in lines[-40:]:
    try:
        j = json.loads(l)
        lvl = j.get("level", "")
        msg = (j.get("msg") or j.get("message") or "")
        # nested message field
        if not msg and isinstance(j.get("message"), str):
            msg = j["message"]
        t = j.get("time") or j.get("timestamp", "")
        flag = ""
        if lvl in (40, 50, "warn", "error") or "error" in str(lvl).lower():
            flag = " <<<"
            err_count += 1
        print(f"[{str(t)[-13:]}] lvl={lvl} {msg[:110]}{flag}")
    except Exception:
        print("RAW:", l[:110])
print(f"\nwarn/error lines in last 40: {err_count}")

# 3. any 'accounts unavailable' in the very last 300 lines?
recent = lines[-300:]
unavail = [l for l in recent if "accounts unavailable" in l]
print(f"'accounts unavailable' in last 300 lines: {len(unavail)}")
if unavail:
    for l in unavail[-3:]:
        try:
            j = json.loads(l)
            print("  last:", j.get("time"), (j.get("msg") or "")[:80])
        except Exception:
            pass
