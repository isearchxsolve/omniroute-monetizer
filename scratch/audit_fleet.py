import requests
import json
import time

BASE_URL = "http://localhost:20128"
s = requests.Session()
s.post(f"{BASE_URL}/api/auth/login", json={"<REDACTED>"})

conns = s.get(f"{BASE_URL}/api/providers").json().get("connections", [])
print(f"Total connections to audit: {len(conns)}")

healthy = []
unhealthy = []

for c in conns:
    cid = c.get("id")
    provider = c.get("provider")
    name = c.get("name")
    try:
        t0 = time.time()
        test_r = s.post(f"{BASE_URL}/api/providers/{cid}/test", timeout=15)
        elapsed = round(time.time() - t0, 3)
        res = test_r.json() if test_r.status_code == 200 else {}
        is_valid = res.get("valid", False)
        diag = res.get("diagnosis", {})
        if is_valid or diag.get("type") == "ok":
            print(f"[OK] {provider} ({name}) -> valid ({elapsed}s)")
            healthy.append({"id": cid, "provider": provider, "name": name, "latency": elapsed})
        else:
            diag_type = diag.get("type", "unknown")
            msg = diag.get("message", res.get("error", "failed"))
            print(f"[FAIL] {provider} ({name}) -> {diag_type}: {str(msg)[:60]}")
            unhealthy.append({"id": cid, "provider": provider, "name": name, "diagnosis": diag_type, "error": str(msg)})
    except Exception as e:
        print(f"[ERROR] {provider} ({name}) -> {e}")
        unhealthy.append({"id": cid, "provider": provider, "name": name, "diagnosis": "timeout", "error": str(e)})

print(f"\nAudit Complete: {len(healthy)} healthy/active, {len(unhealthy)} unhealthy.")
with open("state/fleet_audit.json", "w", encoding="utf-8") as f:
    json.dump({"healthy": healthy, "unhealthy": unhealthy}, f, indent=2)
