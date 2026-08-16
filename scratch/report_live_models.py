"""READ-ONLY report: current live working models + their alias/combo mapping."""
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

# provider status
rp = s.get(f"{BASE}/api/providers", timeout=45).json()
conns = rp.get("connections", [])
prov_status = {}
for c in conns:
    p = c.get("provider")
    if c.get("isActive"):
        prov_status[p] = "LIVE"
    else:
        prov_status.setdefault(p, "DOWN")

# combos
rc = s.get(f"{BASE}/api/combos", timeout=45).json()
combos = rc.get("combos", rc if isinstance(rc, list) else [])
combos.sort(key=lambda c: c.get("sortOrder", 99))

CORE_ALIASES = {"frontier", "auto/best-coding", "auto/best-reasoning", "auto/best-chat", "kimi-coding"}

print("=" * 90)
print("COMBO / ALIAS -> MODELS (provider live-status)")
print("=" * 90)
for c in combos:
    name = c.get("name")
    tag = "  [CORE ALIAS]" if name in CORE_ALIASES else ""
    models = c.get("models", [])
    print(f"\n### {name}{tag}  ({len(models)} models, strategy={c.get('strategy')})")
    for m in models:
        model = m.get("model"); pid = m.get("providerId") or ""
        w = m.get("weight")
        st = prov_status.get(pid, "NO-CONN")
        mark = "LIVE" if st == "LIVE" else "DEAD"
        print(f"    [{mark}] w={w:<4} {model}   (provider: {pid})")

# live providers summary
print("\n" + "=" * 90)
print("PROVIDER CONNECTION STATUS (all 56)")
print("=" * 90)
live = sorted([p for p, st in prov_status.items() if st == "LIVE"])
down = sorted([p for p, st in prov_status.items() if st != "LIVE"])
print(f"\nLIVE providers ({len(live)}):")
for p in live:
    print(f"    {p}")
print(f"\nDOWN/inactive providers ({len(down)}):")
for p in down:
    print(f"    {p}")
