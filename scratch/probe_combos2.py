"""Probe combo structure precisely. Read-only."""
import json
import os

import requests

BASE = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if BASE.endswith("/v1"):
    BASE = BASE[:-3]
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "Keross@321")

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"password": PASSWORD}, timeout=15)
assert r.status_code == 200, r.status_code

r = s.get(f"{BASE}/api/combos", timeout=15)
data = r.json()
combos = data.get("combos")
out = {"type": type(combos).__name__}
if isinstance(combos, dict):
    out["keys"] = list(combos.keys())
    out["detail"] = {}
    for k, v in combos.items():
        if isinstance(v, dict):
            models = v.get("models", [])
            out["detail"][k] = {
                "keys": list(v.keys()),
                "strategy": v.get("strategy"),
                "description": v.get("description"),
                "model_count": len(models),
                "models": models[:6],
            }
else:
    out["len"] = len(combos)
    out["first"] = combos[0] if combos else None

path = os.path.join(os.path.dirname(__file__), "probe_combos2_result.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)
print("WROTE", path, "type:", out["type"])
