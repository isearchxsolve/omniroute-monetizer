"""Find when/why openrouter account became unavailable + check credential health API."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)

# 1. scan app.log for openrouter account state transitions
LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

print("=== openrouter state/health lines (deduped, chronological) ===")
seen = set()
for l in lines:
    if "openrouter" not in l.lower():
        continue
    low = l.lower()
    if any(k in low for k in ["unavailable", "available", "cooldown", "health", "invalid", "401", "403", "disabled", "exhaust", "limit", "suspend", "ban", "mark"]):
        try:
            j = json.loads(l)
            msg = (j.get("msg") or "")[:220]
            t = j.get("time", "")
            k = msg[:70]
            if k in seen:
                continue
            seen.add(k)
            print(f"[{t}] {msg}")
        except Exception:
            pass

# 2. try credential health endpoints
print("\n=== credential health API probes ===")
for path in ["/api/credentials/health", "/api/providers/health", "/api/monitoring/credentials", "/api/credentials"]:
    try:
        r = s.get(BASE + path, timeout=15)
        print(f"{path}: {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"{path}: ERR {e}")
