import json

ga = json.load(open("state/evidence/gap_analysis.json", encoding="utf-8"))
print("GAP COUNTS:")
for k, v in sorted(ga["gap_summary"].items(), key=lambda x: -x[1]["count"]):
    print(f"  {k}: {v['count']}  {v['slugs'][:8]}")
print()
print("ACTIONABLE BUCKETS:")
for k, v in ga.get("actionable_buckets", {}).items():
    if v:
        print(f"  {k}: {len(v)} -> {v[:8]}")
