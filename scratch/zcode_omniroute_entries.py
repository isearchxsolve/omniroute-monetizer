"""READ-ONLY: dump the two existing omniroute provider entries from ZCode config."""
import json

cfg = json.load(open(r"C:\Users\Admin\.zcode\v2\config.json", encoding="utf-8"))
for pid, prov in cfg.get("provider", {}).items():
    if str(prov.get("name", "")).lower() == "omniroute":
        red = dict(prov)
        opts = dict(red.get("options", {}))
        if opts.get("apiKey"):
            k = opts["apiKey"]
            opts["apiKey"] = k[:6] + "..." + k[-4:] if len(k) > 12 else "<short>"
        red["options"] = opts
        print(f"=== {pid} ===")
        print(json.dumps(red, indent=2, ensure_ascii=False))
        print()
