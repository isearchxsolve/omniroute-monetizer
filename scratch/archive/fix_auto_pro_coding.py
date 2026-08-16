import json
import requests

BASE = "http://127.0.0.1:20128"

s = requests.Session()
s.post(f"{BASE}/api/auth/login", json={"password": "<REDACTED>"}, timeout=15)

r = s.get(f"{BASE}/api/combos", timeout=15)
data = r.json()
combos = data if isinstance(data, list) else data.get("combos", data.get("data", []))

target = next((c for c in combos if c.get("name") == "auto/pro-coding"), None)
if not target:
    print("auto/pro-coding NOT FOUND")
    raise SystemExit(1)

cid = target["id"]
models = target.get("models") or []
print(f"auto/pro-coding id={cid}, {len(models)} existing entries")

nvidia_entry = {
    "id": "auto/pro-coding_model_nvidia",
    "kind": "model",
    "model": "nvidia/nemotron-3-super-120b-a12b",
    "providerId": "nvidia",
    "weight": 100,
    "priority": 0,
}
# prepend if not already present
if not any(isinstance(m, dict) and m.get("model") == nvidia_entry["model"] for m in models):
    target["models"] = [nvidia_entry] + models
    print("prepended nvidia entry")

put = s.put(f"{BASE}/api/combos/{cid}", json=target, timeout=15)
print("PUT status:", put.status_code)
if put.status_code != 200:
    print(put.text[:400])

# verify routing
import time
body = {"model": "auto/pro-coding", "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5}
t0 = time.time()
resp = s.post(f"{BASE}/v1/chat/completions", json=body, timeout=90)
print(f"auto/pro-coding route test: {resp.status_code} in {time.time()-t0:.1f}s")
if resp.status_code != 200:
    print(resp.text[:300])
