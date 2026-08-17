"""Enumerate TokenRouter's full model catalog with a live key."""
import json
from pathlib import Path

import requests

KEY = "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE"  # key2, live-verified
BASE = "https://api.tokenrouter.com/v1"

r = requests.get(f"{BASE}/models", headers={"Authorization": f"Bearer {KEY}"}, timeout=60)
print(f"GET /models: {r.status_code}")
if r.status_code == 200:
    data = r.json().get("data", [])
    ids = sorted(m.get("id", "") for m in data if m.get("id"))
    print(f"models: {len(ids)}")
    for i in ids:
        print(f"  {i}")
    Path(r"d:\omniroute-monetizer\state\tokenrouter_models.json").write_text(json.dumps(ids, indent=2))
    print("saved -> state/tokenrouter_models.json")
else:
    print(r.text[:300])
