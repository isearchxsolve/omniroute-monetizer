"""Probe live OmniRoute combo + provider API schemas. Read-only."""
import json
import os
import sys

import requests

BASE = os.environ.get("OMNIROUTE_BASE_URL", "http://localhost:20128").rstrip("/")
if BASE.endswith("/v1"):
    BASE = BASE[:-3]
PASSWORD = os.environ.get("OMNIROUTE_PASSWORD", "Keross@321")

out = {}
s = requests.Session()
try:
    r = s.post(f"{BASE}/api/auth/login", json={"password": PASSWORD}, timeout=15)
    out["login_status"] = r.status_code
    out["has_cookie"] = bool(s.cookies.get("auth_token"))
except Exception as e:
    out["login_error"] = f"{type(e).__name__}: {e}"

if out.get("login_status") == 200:
    try:
        r = s.get(f"{BASE}/api/combos", timeout=15)
        out["combos_status"] = r.status_code
        data = r.json()
        if isinstance(data, dict):
            out["combos_top_keys"] = list(data.keys())
            combos = data.get("combos", data.get("data", []))
        else:
            combos = data
        out["combo_count"] = len(combos)
        if combos:
            c = combos[0]
            out["first_combo_keys"] = list(c.keys())
            out["first_combo_sample"] = json.loads(json.dumps(c))[:0] if False else None
            # store trimmed sample
            sample = {k: c[k] for k in list(c.keys())}
            out["first_combo"] = sample
        # find our target combos
        ids = []
        for c in combos:
            cid = c.get("id") or c.get("name")
            ids.append(cid)
        out["combo_ids"] = ids
    except Exception as e:
        out["combos_error"] = f"{type(e).__name__}: {e}"

    try:
        r = s.get(f"{BASE}/api/providers", timeout=15)
        data = r.json()
        conns = data.get("connections", []) if isinstance(data, dict) else []
        out["providers_status"] = r.status_code
        out["connection_total"] = data.get("total") if isinstance(data, dict) else None
        out["connection_count"] = len(conns)
        # summarize providers
        provs = {}
        for c in conns:
            p = c.get("provider", "?")
            provs.setdefault(p, []).append({
                "id": c.get("id"),
                "authType": c.get("authType"),
                "isActive": c.get("isActive"),
                "testStatus": c.get("testStatus"),
                "has_apiKey": bool(c.get("apiKey")),
            })
        out["providers"] = provs
    except Exception as e:
        out["providers_error"] = f"{type(e).__name__}: {e}"

path = os.path.join(os.path.dirname(__file__), "probe_combos_result.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, default=str)
print("WROTE", path)
print("login:", out.get("login_status"), "combos:", out.get("combos_status"), "providers:", out.get("providers_status"))
