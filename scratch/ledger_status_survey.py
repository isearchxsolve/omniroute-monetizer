import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "state" / "all_296_providers_execution_ledger.json").read_text(encoding="utf-8"))
ps = d["providers"] if isinstance(d, dict) and "providers" in d else d

print("total:", len(ps))

sc = Counter()
for k, v in ps.items():
    sc[(v.get("status"), v.get("classification"))] += 1

print("\n=== status / classification counts ===")
for (s, c), n in sorted(sc.items(), key=lambda x: -x[1]):
    print(f"{n:4d}  status={s}  class={c}")

# group by status only
print("\n=== by status ===")
s_only = Counter(v.get("status") for v in ps.values())
for s, n in sorted(s_only.items(), key=lambda x: -x[1]):
    print(f"{n:4d}  {s}")
