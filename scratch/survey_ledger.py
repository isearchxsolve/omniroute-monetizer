import json, collections

with open("state/all_296_providers_execution_ledger.json", encoding="utf-8") as f:
    data = json.load(f)

providers = data["providers"]
print(f"TOTAL providers in ledger: {len(providers)}")

# Inspect one entry's keys
first = providers[0] if isinstance(providers, list) else next(iter(providers.values()))
print("\nSample entry keys:", sorted(first.keys()))

# Classify by status field
def get_status(p):
    for k in ("status", "classification", "state", "class"):
        if k in p:
            return p[k]
    return "NO_STATUS_FIELD"

statuses = collections.Counter(get_status(p) for p in (providers if isinstance(providers, list) else providers.values()))
print("\n=== Status distribution ===")
for s, c in statuses.most_common():
    print(f"  {c:4d}  {s}")
