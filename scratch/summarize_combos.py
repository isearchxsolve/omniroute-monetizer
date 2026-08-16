import json

data = json.load(open(r"d:\omniroute-monetizer\scratch\probe_combos_raw.json", encoding="utf-8"))
lines = []
for i, c in enumerate(data["combos"]):
    models = c.get("models", [])
    lines.append(f"{i} | name: {c.get('name')} | id: {str(c.get('id'))[:8]} | models: {len(models)} | desc: {(c.get('description') or '')[:60]}")
    for m in models[:4]:
        lines.append(f"     - {m.get('model')} | provider: {m.get('providerId')} | kind: {m.get('kind')}")
open(r"d:\omniroute-monetizer\scratch\combo_summary.txt", "w", encoding="utf-8").write("\n".join(lines))
print("done")
