"""Inspect extraApiKeys / copilotToken contents (masked) for harvestability."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests
from oauth_keepalive import resolve_password

BASE = "http://127.0.0.1:20128"


def mask(v):
    v = str(v)
    return v[:10] + "..." + v[-4:] if len(v) > 16 else f"<{len(v)} chars>"


s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45)
j = s.get(f"{BASE}/api/providers", timeout=90).json()
conns = j.get("connections", [])

for x in conns:
    if not x.get("isActive"):
        continue
    psd = x.get("providerSpecificData")
    if isinstance(psd, str):
        try:
            psd = json.loads(psd)
        except Exception:
            continue
    if not isinstance(psd, dict):
        continue
    prov = x.get("provider")
    for field in ("extraApiKeys", "copilotToken"):
        if field in psd:
            val = psd[field]
            if isinstance(val, list):
                print(f"{prov}.{field}: list of {len(val)}")
                for i, item in enumerate(val[:5]):
                    if isinstance(item, dict):
                        print(f"   [{i}] keys={list(item.keys())} "
                              + " ".join(f"{k}={mask(v)}" for k, v in item.items()
                                         if isinstance(v, (str, int)) and k.lower() not in ("apikeyhealth",)))
                    else:
                        print(f"   [{i}] {mask(item)}")
            elif isinstance(val, str):
                print(f"{prov}.{field}: {mask(val)}")
            else:
                print(f"{prov}.{field}: {type(val).__name__}")
