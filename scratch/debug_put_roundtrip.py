import json, sqlite3, time
import requests

BASE = "http://127.0.0.1:20128"
NVIDIA_MODEL = "nvidia/nemotron-3-super-120b-a12b"

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

# Step 1: prove a no-op GET->PUT round-trip works on one combo
name, cid = "auto/pro-coding", OLD_COMBOS["auto/pro-coding"]
r = s.get(f"{BASE}/api/combos", timeout=15)
combos = r.json()["combos"]
live = next((c for c in combos if c.get("id") == cid), None)
print("live entry found:", live is not None)
if live:
    print("live keys:", sorted(live.keys()))
    print("live models count:", len(live.get("models") or []))
    noop = s.put(f"{BASE}/api/combos/{cid}", json=live, timeout=15)
    print("NO-OP PUT status:", noop.status_code, noop.text[:200] if noop.status_code != 200 else "OK")
con.close()
