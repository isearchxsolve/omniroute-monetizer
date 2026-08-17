"""Reconstruct original field values for over-matched entries from sibling entries."""
import json

d = json.load(open("state/all_296_providers_execution_ledger.json", encoding="utf-8"))
provs = d["providers"] if isinstance(d, dict) and "providers" in d else d

MARK = "E2E VERIFIED 2026-08-18"

# 1. siblings with same 402 blocker (for g4f-gemini)
print("=== entries with HTTP 402 blocker:")
for k, v in provs.items():
    if isinstance(v, dict) and "402" in str(v.get("details", {}).get("blocker", "")):
        print(f"  {k}: status={v.get('status')} verdict={v.get('verdict')} observed={v.get('observed_verdict')}")

# 2. siblings with same 'Requires user registration' blocker (for gemini-business)
print("=== entries with 'Requires user registration' blocker (first 8):")
n = 0
for k, v in provs.items():
    if isinstance(v, dict) and "Requires user registration" in str(v.get("details", {}).get("blocker", "")):
        print(f"  {k}: status={v.get('status')} verdict={v.get('verdict')} observed={v.get('observed_verdict')}")
        n += 1
        if n >= 8:
            break

# 3. siblings with verified_upstream (for gemini evidence pattern)
print("=== entries with verified_upstream=true (first 5):")
n = 0
for k, v in provs.items():
    if isinstance(v, dict) and v.get("verified_upstream") is True:
        print(f"  {k}: status={v.get('status')} verdict={v.get('verdict')} evidence={str(v.get('evidence'))[:120]!r}")
        n += 1
        if n >= 5:
            break

# 4. status_counts if present
if isinstance(d, dict):
    for key in ("status_counts", "summary", "meta"):
        if key in d:
            print(f"=== {key}:", json.dumps(d[key], ensure_ascii=False)[:800])
