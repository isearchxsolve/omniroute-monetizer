import json, sqlite3, time
import requests

BASE = "http://127.0.0.1:20128"
NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# ids from DB
OLD_COMBOS = {
    "auto/pro-coding": "66e7fa63-0bd4-4d46-b06e-3669d407459c",
    "Frontier Max": "4a4de0d2-fba6-45d4-a74d-5f06b196c300",
    "auto/free-chat": "7e521395-b148-4755-903a-4d3152d44019",
    "auto/asian-flagships": "b12c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
}

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
con = sqlite3.connect("file:" + db.replace("\\", "/") + "?mode=ro", uri=True)
cur = con.cursor()

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": "<REDACTED>"}, timeout=15)

def convert_entry(e, idx, combo_name):
    """Convert old-schema entry {name, weight, priority} to new schema."""
    if isinstance(e, str):
        model = e.strip()
    elif isinstance(e, dict):
        model = (e.get("model") or e.get("name") or "").strip()
    else:
        return None
    if not model or "/" not in model:
        return None
    provider = model.split("/", 1)[0].strip()
    weight = e.get("weight", 0) if isinstance(e, dict) else 0
    return {
        "id": f"{combo_name}_model_{idx}",
        "kind": "model",
        "model": model,
        "providerId": provider,
        "weight": weight,
    }

for name, cid in OLD_COMBOS.items():
    row = cur.execute("SELECT data, sort_order FROM combos WHERE id=?", (cid,)).fetchone()
    if not row:
        print(f"{name}: DB row not found!")
        continue
    data = json.loads(row[0])
    sort_order = row[1] if isinstance(row[1], int) else 1

    old_models = data.get("models") or []
    converted = []
    for i, e in enumerate(old_models):
        c = convert_entry(e, i, name.replace("/", "-").replace(" ", "-").lower())
        if c:
            converted.append(c)

    # add nvidia fallback at the end if not present
    if not any(m["model"] == NVIDIA_MODEL for m in converted):
        converted.append({
            "id": f"{name.replace('/', '-').replace(' ', '-').lower()}_model_nvidia_fallback",
            "kind": "model",
            "model": NVIDIA_MODEL,
            "providerId": "nvidia",
            "weight": 1,
        })

    new_data = {
        "name": name,
        "description": data.get("description", ""),
        "models": converted,
        "strategy": data.get("strategy", "priority"),
        "config": {
            "maxRetries": data.get("retries", 3),
            "retryDelayMs": data.get("retry_delay", 500),
        },
        "id": cid,
        "isHidden": data.get("isHidden", False),
        "sortOrder": sort_order if isinstance(sort_order, int) else 1,
        "version": 2,
    }

    put = s.put(f"{BASE}/api/combos/{cid}", json=new_data, timeout=15)
    print(f"{name}: {len(old_models)} old entries -> {len(converted)} converted, PUT {put.status_code}")
    if put.status_code != 200:
        print("  ", put.text[:300])

con.close()

# verify routing for all 4
print("\n--- routing verification ---")
for name in OLD_COMBOS:
    body = {"model": name, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5}
    t0 = time.time()
    try:
        resp = s.post(f"{BASE}/v1/chat/completions", json=body, timeout=120)
        print(f"{name}: {resp.status_code} in {time.time()-t0:.1f}s")
        if resp.status_code != 200:
            print("   ", resp.text[:200])
    except Exception as ex:
        print(f"{name}: EXC {ex}")
