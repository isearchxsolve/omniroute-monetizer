import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
d = json.loads((ROOT / "state" / "all_296_providers_execution_ledger.json").read_text(encoding="utf-8"))
ps = d["providers"] if isinstance(d, dict) and "providers" in d else d

# Next actionable sets
for target_status in ["BLOCKED_UNVERIFIED", "BLOCKED_INFERENCE_FAILED", "BLOCKED_NO_SESSION",
                      "BLOCKED_CONNECTION_UNVERIFIED", "BLOCKED_BROWSER_SESSION", "BLOCKED_RATE_LIMITED"]:
    items = [(k, v) for k, v in ps.items() if v.get("status") == target_status]
    print(f"\n===== {target_status} ({len(items)}) =====")
    for k, v in items:
        print(f"  {k:30s} note={str(v.get('note',''))[:90]}")
