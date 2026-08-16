"""Verify the openrouter key upstream + scan app.log for openrouter auth errors."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=15)
conns = s.get(f"{BASE}/api/providers", timeout=30).json().get("connections", [])
or_conn = [c for c in conns if c.get("provider") == "openrouter"][0]
key = or_conn.get("apiKey") or ""
print(f"openrouter key: len={len(key)} prefix={key[:10]!r} suffix={key[-4:]!r}")

# verify upstream
r = requests.get("https://openrouter.ai/api/v1/auth/key",
                 headers={"Authorization": f"Bearer {key}"}, timeout=30)
print("upstream /auth/key status:", r.status_code)
print("upstream body:", r.text[:400])

# scan app.log for openrouter errors today
LOG = r"C:\Users\Admin\.omniroute\logs\application\app.log"
with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    lines = f.read().splitlines()

hits = []
for l in lines[-8000:]:
    if "openrouter" in l.lower() and ("401" in l or "403" in l or "invalid" in l.lower() or "unavailable" in l.lower() or "unauthorized" in l.lower() or "credential" in l.lower()):
        hits.append(l)
print(f"\nopenrouter error-ish lines in last 8000: {len(hits)}")
seen = set()
for h in hits[-12:]:
    try:
        j = json.loads(h)
        msg = (j.get("msg") or "")[:250]
        t = j.get("time", "")
        k = msg[:60]
        if k in seen:
            continue
        seen.add(k)
        print(f"[{t}] {msg}")
    except Exception:
        print(h[:250])
