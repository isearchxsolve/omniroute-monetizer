import json, sys
import requests

BASE = "http://127.0.0.1:20128"
UUID = "574246f2-1cdf-48ad-83b6-2ca1b541f8e4"

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": "Keross@321"}, timeout=15)
r.raise_for_status()
print("login ok")

r = s.get(f"{BASE}/api/combos", timeout=15)
r.raise_for_status()
data = r.json()
combos = data if isinstance(data, list) else data.get("combos", data.get("data", []))
print(f"fetched {len(combos)} combos")

fixed = []
for c in combos:
    cid = c.get("id")
    name = c.get("name")
    models = c.get("models") or []
    changed = False
    for m in models:
        if isinstance(m, dict) and m.get("providerId") == UUID:
            m["providerId"] = "nvidia"
            changed = True
    if changed:
        put = s.put(f"{BASE}/api/combos/{cid}", json=c, timeout=15)
        status = put.status_code
        ok = status == 200
        print(f"  {name}: providerId fixed -> PUT {status}")
        if ok:
            fixed.append(name)
        else:
            print("    body:", put.text[:300])

print(f"\nfixed {len(fixed)} combos: {fixed}")
