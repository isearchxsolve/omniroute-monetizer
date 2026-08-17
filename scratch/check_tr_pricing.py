"""Check TokenRouter /models for pricing fields to identify truly FREE models."""
import json
from pathlib import Path

import requests

KEYS = [
    "sk-5qUyoiQoJKptZl72riS51UzVNPCxHvYgiB3nLHu31PtGyswE",  # key2
    "sk-d8x2mCrBuUw6v6kNnPRMwJj1QCYqCSNItdHgBFNfsJIGECjN",  # key3
    "sk-CrkSNvqBOFQl0dhRf6y1sX3qyWy5fi4OPX4snuIiAacLeuTU",  # key4
]

import time

payload = None
for attempt in range(6):
    KEY = KEYS[attempt % len(KEYS)]
    r = requests.get(
        "https://api.tokenrouter.com/v1/models",
        headers={"Authorization": f"Bearer {KEY}"},
        timeout=60,
    )
    print(f"attempt {attempt + 1} (key{2 + (attempt % 3)}): {r.status_code}")
    if r.status_code == 200:
        payload = r.json()
        break
    time.sleep(5)

if payload is None:
    raise SystemExit("all attempts failed")
data = payload.get("data", [])
print(f"models: {len(data)}")

# inspect full structure of first entry
print("\nfull first entry:")
print(json.dumps(data[0], indent=2)[:800])

# collect all field names across entries
fields = set()
for m in data:
    fields.update(m.keys())
print(f"\nall fields: {sorted(fields)}")

# find pricing-like fields and free models
free = []
for m in data:
    mid = m.get("id", "")
    pricing = m.get("pricing")
    if isinstance(pricing, dict):
        prompt = float(pricing.get("prompt", pricing.get("input", -1)) or 0)
        completion = float(pricing.get("completion", pricing.get("output", -1)) or 0)
        if prompt == 0 and completion == 0:
            free.append(mid)
    elif "free" in mid.lower():
        free.append(mid)

print(f"\nFREE models (zero pricing or -free suffix): {len(free)}")
for f in free:
    print(f"  {f}")

Path(r"d:\omniroute-monetizer\state\tokenrouter_free_models.json").write_text(json.dumps(free, indent=2))
print("\nsaved -> state/tokenrouter_free_models.json")
