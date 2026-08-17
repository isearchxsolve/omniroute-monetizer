"""Re-activate the free OpenRouter connection (PUT isActive=true)."""
import sys

sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

CONN_ID = "49aa144d-9005-4968-a6cd-a36e8a2e947f"

api = OmniRouteAPI()
api.login()

# current state
r = api.session.get(f"{api.api}/providers", timeout=60)
r.raise_for_status()
conns = r.json().get("connections", [])
target = next((c for c in conns if c.get("id") == CONN_ID), None)
if not target:
    print("connection not found!")
    sys.exit(1)
print("before: isActive =", target.get("isActive"), "| provider =", target.get("provider"),
      "| testStatus =", target.get("testStatus"))

# re-activate
payload = dict(target)
payload["isActive"] = True
for k in ("testStatus", "lastTestedAt", "testError"):
    payload.pop(k, None)
r2 = api.session.put(f"{api.api}/providers/{CONN_ID}", json=payload, timeout=120)
print("PUT status:", r2.status_code)
print("PUT body:", r2.text[:500])

# verify
r3 = api.session.get(f"{api.api}/providers", timeout=60)
after = next((c for c in r3.json().get("connections", []) if c.get("id") == CONN_ID), None)
print("after: isActive =", after.get("isActive"), "| testStatus =", after.get("testStatus"))
