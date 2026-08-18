import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

MIMO = "7bc51c6c-1aed-488a-ac64-90141658aafe"

# Sync models for the connection
r = api.session.post(f"{api.api}/providers/{MIMO}/sync-models", timeout=60)
print("sync-models:", r.status_code, r.text[:300])

# List models for the connection
r2 = api.session.get(f"{api.api}/providers/{MIMO}/models", timeout=60)
print("models:", r2.status_code, r2.text[:400])

# E2E again
r3 = api.session.post(api.v1 + "/chat/completions",
    json={"model": "mimocode/mimo-auto",
          "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
          "max_tokens": 60, "stream": False}, timeout=120)
print("E2E:", r3.status_code, r3.text[:300])
