"""Recompute status_counts in the 296-provider ledger from actual statuses."""
import collections
import json

LEDGER = "state/all_296_providers_execution_ledger.json"

d = json.load(open(LEDGER, encoding="utf-8"))
counts = collections.Counter(v["status"] for v in d["providers"].values())
d["status_counts"] = dict(sorted(counts.items(), key=lambda kv: -kv[1]))
json.dump(d, open(LEDGER, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("providers:", len(d["providers"]))
print(json.dumps(d["status_counts"], indent=1))
