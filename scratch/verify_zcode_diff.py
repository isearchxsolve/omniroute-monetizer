"""VERIFY: diff backup vs new ZCode config — only omniroute entries may differ."""
import json

bak = json.load(open(r"d:\omniroute-monetizer\state\zcode_config_backup_20260816_204801.json", encoding="utf-8"))
new = json.load(open(r"C:\Users\Admin\.zcode\v2\config.json", encoding="utf-8"))

assert list(bak.keys()) == list(new.keys()) == ["provider"], "top-level keys changed!"
bp, np_ = bak["provider"], new["provider"]
assert set(bp.keys()) == set(np_.keys()), "provider set changed!"

changed, untouched = [], []
for pid in bp:
    if bp[pid] == np_[pid]:
        untouched.append(pid)
    else:
        changed.append(pid)

print(f"providers unchanged: {len(untouched)}/21")
print(f"providers changed : {len(changed)}")
for pid in changed:
    b, n = bp[pid], np_[pid]
    print(f"\n  {pid} (name={n.get('name')!r}):")
    # options identical?
    print(f"    options identical: {b.get('options') == n.get('options')}")
    bm, nm = b.get("models", {}), n.get("models", {})
    kept = [m for m in bm if m in nm and bm[m] == nm[m]]
    added = [m for m in nm if m not in bm]
    removed = [m for m in bm if m not in nm]
    print(f"    models kept intact: {len(kept)} {kept}")
    print(f"    models added      : {len(added)}")
    print(f"    models removed    : {len(removed)} {removed}")
    other_b = {k: v for k, v in b.items() if k != "models"}
    other_n = {k: v for k, v in n.items() if k != "models"}
    print(f"    non-model fields identical: {other_b == other_n}")
