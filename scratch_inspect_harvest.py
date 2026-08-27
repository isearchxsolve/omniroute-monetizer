import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = json.load(open(r"d:\omniroute-monetizer\state\secrets\expired_seat_reauth_harvest.json", encoding="utf-8"))
for seat, info in d.items():
    print(f"\n=== {seat}")
    if "error" in info:
        print("  ERROR:", info["error"]); continue
    for c in info.get("cookies", []):
        v = c.get("value", "")
        print(f"  {c['name']:32s} len={len(v):5d} httpOnly={c.get('httpOnly')} val={v[:50]}")
