import json, sqlite3, datetime

db = r"C:\Users\Admin\.omniroute\storage.sqlite"
NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"

OLD_COMBOS = {
    "auto/pro-coding": "66e7fa63-0bd4-4d46-b06e-3669d407459c",
    "Frontier Max": "4a4de0d2-fba6-45d4-a74d-5f06b196c300",
    "auto/free-chat": "7e521395-b148-4755-903a-4d3152d44019",
    "auto/asian-flagships": "b12c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
}

def slug(name):
    return name.replace("/", "-").replace(" ", "-").lower()

con = sqlite3.connect(db, timeout=30)
cur = con.cursor()
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.datetime.utcnow().microsecond//1000:03d}Z"

for name, cid in OLD_COMBOS.items():
    row = cur.execute("SELECT data, sort_order, name FROM combos WHERE id=?", (cid,)).fetchone()
    if not row:
        print(f"{name}: row missing, skip")
        continue
    old = json.loads(row[0])
    sort_order = row[1] if isinstance(row[1], int) else 1
    old_models = old.get("models") or []

    new_models = []
    # nvidia first so it routes reliably while OAuth providers are inactive
    new_models.append({
        "id": f"{slug(name)}_model_nvidia",
        "kind": "model",
        "model": NVIDIA_MODEL,
        "providerId": "nvidia",
        "weight": 1000,
        "priority": 0,
    })
    idx = 1
    for e in old_models:
        model = (e.get("model") or e.get("name") or "").strip() if isinstance(e, dict) else str(e).strip()
        if not model or "/" not in model or model == NVIDIA_MODEL:
            continue
        provider = model.split("/", 1)[0].strip()
        new_models.append({
            "id": f"{slug(name)}_model_{idx}",
            "kind": "model",
            "model": model,
            "providerId": provider,
            "weight": e.get("weight", 0) if isinstance(e, dict) else 0,
            "priority": e.get("priority", idx) if isinstance(e, dict) else idx,
        })
        idx += 1

    new_data = {
        "name": name,
        "description": old.get("description", ""),
        "models": new_models,
        "strategy": old.get("strategy", "priority"),
        "id": cid,
        "config": {
            "maxRetries": old.get("retries", 3),
            "retryDelayMs": old.get("retry_delay", 500),
        },
        "isHidden": old.get("isHidden", False),
        "sortOrder": sort_order,
        "version": 2,
    }

    cur.execute(
        "UPDATE combos SET data=?, name=?, sort_order=?, updated_at=? WHERE id=?",
        (json.dumps(new_data), name, sort_order, now, cid),
    )
    # fix bad created_at ('500' or non-ISO) if present
    ca = cur.execute("SELECT created_at FROM combos WHERE id=?", (cid,)).fetchone()[0]
    if not ca or not str(ca).startswith("20"):
        cur.execute("UPDATE combos SET created_at=? WHERE id=?", (now, cid))
        print(f"  fixed created_at (was {ca!r})")
    print(f"{name}: {len(old_models)} old -> {len(new_models)} new models, UPDATE rowcount={cur.rowcount}")

con.commit()
con.close()
print("committed.")
