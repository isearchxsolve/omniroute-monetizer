"""READ-ONLY: dump all combos + every model they reference, cross-ref vs live catalog."""
import json
import sys

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
import requests

BASE = "http://127.0.0.1:20128"
from oauth_keepalive import resolve_password

import time

s = requests.Session()
# login can also stall during catalog rebuild — retry
r = None
for attempt in range(5):
    try:
        r = s.post(f"{BASE}/api/auth/login", json={"password": resolve_password()}, timeout=45)
        break
    except Exception as e:
        print(f"  login attempt {attempt+1} failed: {type(e).__name__}, retrying in 10s...")
        time.sleep(10)
if r is None:
    print("FATAL: could not login")
    sys.exit(1)
print("login:", r.status_code)

# 1. live model catalog (what /v1/models actually serves)
# NOTE: /v1/models can stall ~30s during catalog rebuild (Blocker #3) — retry.
cat = None
for attempt in range(4):
    try:
        cat = s.get(f"{BASE}/v1/models", timeout=60).json()
        break
    except Exception as e:
        print(f"  /v1/models attempt {attempt+1} failed: {type(e).__name__}, retrying in 8s...")
        import time
        time.sleep(8)
if cat is None:
    print("FATAL: could not fetch catalog")
    sys.exit(1)
models = cat.get("data", cat if isinstance(cat, list) else [])
live_ids = set()
for m in models:
    mid = m.get("id") if isinstance(m, dict) else m
    if mid:
        live_ids.add(mid)
print(f"\n=== LIVE CATALOG: {len(live_ids)} model ids ===")

# 2. combos via API
rc = s.get(f"{BASE}/api/combos", timeout=30)
print("GET /api/combos:", rc.status_code)
combos = rc.json()
# normalize shape
if isinstance(combos, dict):
    arr = combos.get("combos") or combos.get("data") or combos.get("items") or []
else:
    arr = combos
print(f"combos count: {len(arr)}")

# 3. for each combo, extract model entries (models are TOP-LEVEL, not under data)
print("\n=== PER-COMBO MODEL REFERENCES ===")
all_refs = {}  # model -> list of (combo_name, providerId)
for c in arr:
    cid = c.get("id")
    name = c.get("name")
    mlist = c.get("models", [])
    strategy = c.get("strategy")
    print(f"\n--- combo id={cid} name={name!r} models={len(mlist)} strategy={strategy}")
    for e in mlist:
        if not isinstance(e, dict):
            continue
        model = e.get("model")
        pid = e.get("providerId") or e.get("provider")
        kind = e.get("kind")
        prio = e.get("priority")
        weight = e.get("weight")
        in_cat = model in live_ids
        flag = "" if in_cat else "  <<< NOT IN CATALOG"
        print(f"    [p={prio} w={weight}] {model!r} providerId={pid!r} kind={kind}{flag}")
        all_refs.setdefault(model, []).append((name, pid))

# 4. summary: which referenced models are NOT in live catalog
print("\n=== REFERENCED MODELS MISSING FROM LIVE CATALOG ===")
missing = {m: refs for m, refs in all_refs.items() if m not in live_ids}
if not missing:
    print("(none — every referenced model is in the live catalog)")
else:
    for m, refs in sorted(missing.items()):
        print(f"  {m!r}  -> used by: {refs}")

# 5. also dump raw combos JSON to a file for inspection
with open(r"d:\omniroute-monetizer\state\combos_dump.json", "w", encoding="utf-8") as f:
    json.dump(arr, f, indent=2, default=str)
print(f"\nwrote state/combos_dump.json ({len(arr)} combos)")

# 6. dump live catalog ids too
with open(r"d:\omniroute-monetizer\state\live_catalog_ids.json", "w", encoding="utf-8") as f:
    json.dump(sorted(live_ids), f, indent=2)
print(f"wrote state/live_catalog_ids.json ({len(live_ids)} ids)")
