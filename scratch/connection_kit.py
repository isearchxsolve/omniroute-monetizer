"""READ-ONLY: report OmniRoute client connection kit — base URL, API key, model IDs (combos)."""
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

# 1. combos = the alias model IDs
rc = s.get(f"{BASE}/api/combos", timeout=45).json()
combos = rc.get("combos", rc if isinstance(rc, list) else [])
print("=== COMBOS (alias model IDs) ===")
for c in combos:
    print(f"  {c.get('name')!r}  id={c.get('id')}  models={len(c.get('models', []))}")

# 2. /v1/models — what the OpenAI-compatible endpoint actually exposes
print("\n=== /v1/models (no auth attempt) ===")
try:
    r = requests.get(f"{BASE}/v1/models", timeout=45)
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        ids = [m.get("id") for m in r.json().get("data", [])]
        print(f"  count={len(ids)}")
        for i in ids[:60]:
            print(f"    {i}")
        if len(ids) > 60:
            print(f"    ... +{len(ids)-60} more")
    else:
        print("  ", r.text[:200])
except Exception as e:
    print("  EXC:", type(e).__name__, e)

# 3. settings — look for API key config
print("\n=== /api/settings (auth) — key-ish fields ===")
try:
    r = s.get(f"{BASE}/api/settings", timeout=45)
    print(f"  status={r.status_code}")
    if r.status_code == 200:
        j = r.json()
        def walk(o, path=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    p = f"{path}.{k}" if path else k
                    if any(t in k.lower() for t in ("key", "token", "auth", "bearer", "secret")):
                        sv = str(v)
                        print(f"    {p} = {sv[:6]}...({len(sv)} chars)" if len(sv) > 10 else f"    {p} = {sv}")
                    else:
                        walk(v, p)
            elif isinstance(o, list):
                for i, v in enumerate(o[:5]):
                    walk(v, f"{path}[{i}]")
        walk(j)
except Exception as e:
    print("  EXC:", type(e).__name__, e)
