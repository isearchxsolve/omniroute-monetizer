import json
from pathlib import Path

r = json.load(open(Path(__file__).parent / "lasthelp_divergence_report.json"))
for k, v in r.items():
    ol = v.get("only_lasthelp", [])
    print(f"\n=== {k} === ONLY_LASTHELP ({len(ol)}):")
    for f in ol:
        print("  +", f)
