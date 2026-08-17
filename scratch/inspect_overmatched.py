"""Inspect original verdicts for g4f-gemini, gemini, gemini-business from the #112 scan + current ledger fields."""
import json

scan = json.load(open("state/provider_upstream_scan.json", encoding="utf-8"))
ledger = json.load(open("state/all_296_providers_execution_ledger.json", encoding="utf-8"))

targets = ["g4f-gemini", "gemini", "gemini-business", "gemini-web"]

# scan structure unknown: find entries
def find_in(obj, name):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == name or (isinstance(v, dict) and (v.get("provider") == name or v.get("id") == name)):
                out.append((k, v))
            elif isinstance(v, (dict, list)):
                out.extend(find_in(v, name))
    elif isinstance(obj, list):
        for e in obj:
            if isinstance(e, dict) and (e.get("provider") == name or e.get("id") == name or e.get("key") == name):
                out.append((name, e))
            elif isinstance(e, (dict, list)):
                out.extend(find_in(e, name))
    return out

print("=== scan file top-level type:", type(scan).__name__)
if isinstance(scan, dict):
    print("scan keys:", list(scan.keys())[:10])

for t in targets:
    print(f"\n--- SCAN {t}:")
    for k, v in find_in(scan, t)[:2]:
        print(json.dumps(v, ensure_ascii=False)[:600])
    print(f"--- LEDGER {t}:")
    for k, v in find_in(ledger, t)[:2]:
        print(json.dumps(v, ensure_ascii=False)[:800])
