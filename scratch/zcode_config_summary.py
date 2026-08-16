"""READ-ONLY: summarize ZCode config.json structure + providers."""
import json

c = json.load(open(r"C:\Users\Admin\.zcode\v2\config.json", encoding="utf-8"))
print("top-level keys:", list(c.keys()))
provs = c.get("provider", {})
print(f"providers: {len(provs)}")
for k, v in provs.items():
    print(f"  {k}")
    print(f"     name={v.get('name')!r} kind={v.get('kind')!r} enabled={v.get('enabled')} source={v.get('source')!r}")
    print(f"     baseURL={v.get('options', {}).get('baseURL')!r}")
    print(f"     models={list(v.get('models', {}).keys())}")
# any omniroute mention?
raw = open(r"C:\Users\Admin\.zcode\v2\config.json", encoding="utf-8").read()
print("\nomniroute mentioned:", "omniroute" in raw.lower(), "| 20128 mentioned:", "20128" in raw)
