"""READ-ONLY: authoritative dead-model detection via PROVIDER STATUS, not catalog.
A combo model is truly dead only if its provider connection is inactive/dead."""
import json, sys, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

s = requests.Session()
for a in range(5):
    try:
        s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45); break
    except Exception as e:
        print(f"login retry {a+1}: {type(e).__name__}"); time.sleep(10)

# 1. all provider connections + status
rp = s.get(f"{BASE}/api/providers", timeout=45).json()
conns = rp.get("connections", [])
print(f"total connections: {len(conns)}")

# index by provider name -> list of conn status
by_prov = {}
for c in conns:
    prov = c.get("provider")
    by_prov.setdefault(prov, []).append({
        "id": c.get("id"),
        "isActive": c.get("isActive"),
        "testStatus": c.get("testStatus"),
        "authType": c.get("authType"),
    })

# 2. combos
rc = s.get(f"{BASE}/api/combos", timeout=45).json()
arr = rc.get("combos", rc if isinstance(rc, list) else [])

# 3. for each combo model, resolve provider status
print("\n=== COMBO MODELS vs PROVIDER STATUS ===")
dead = []   # (combo, model, providerId, reason)
for c in arr:
    name = c.get("name")
    mlist = c.get("models", [])
    print(f"\n--- {name!r} ({len(mlist)} models)")
    for e in mlist:
        if not isinstance(e, dict): continue
        model = e.get("model"); pid = e.get("providerId") or e.get("provider")
        w = e.get("weight")
        pconns = by_prov.get(pid, [])
        if not pconns:
            status = "NO_CONNECTION"
            active = False
        else:
            actives = [x for x in pconns if x["isActive"]]
            if actives:
                status = "ACTIVE(" + ",".join(str(x["testStatus"]) for x in actives) + ")"
                active = True
            else:
                status = "INACTIVE(" + ",".join(str(x["testStatus"]) for x in pconns) + ")"
                active = False
        flag = ""
        if not active:
            flag = "  <<< DEAD (provider not active)"
            dead.append((name, model, pid, status))
        print(f"    [w={w}] {model!r} prov={pid!r} -> {status}{flag}")

print("\n=== TRULY DEAD COMBO MODELS (provider inactive/no connection) ===")
if not dead:
    print("(none — every combo model's provider is active)")
else:
    for name, model, pid, status in dead:
        print(f"  {name!r}: {model!r} (provider {pid!r}: {status})")

# 4. dump provider status index for reference
with open(r"d:\omniroute-monetizer\state\provider_status_index.json","w",encoding="utf-8") as f:
    json.dump(by_prov, f, indent=2, default=str)
print(f"\nwrote state/provider_status_index.json")
