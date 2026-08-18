import json
with open("state/evidence/gap_analysis.json", encoding="utf-8") as f:
    ga = json.load(f)
print("=== TOP ACTIONABLE BUCKETS (examples) ===")
for bucket, examples in ga["actionable_buckets"].items():
    if not examples:
        continue
    print(f"\n{bucket}:")
    for slug in examples[:5]:
        print(f"  - {slug}")
    if len(examples) > 5:
        print(f"  ... and {len(examples)-5} more")