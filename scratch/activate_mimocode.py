import sys, json
sys.path.insert(0, "scripts/automation")
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

MIMO = "7bc51c6c-1aed-488a-ac64-90141658aafe"

# Activate the mimocode connection
res = api.update_connection(MIMO, {"isActive": True})
print("activate mimocode:", res.get("http_status"), str(res.get("body"))[:150])

# Test connection
tc = api.test_connection(MIMO)
print("test mimocode:", tc.get("http_status"), str(tc.get("result"))[:200])

# E2E
r = api.session.post(api.v1 + "/chat/completions",
    json={"model": "mimocode/mimo-auto",
          "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
          "max_tokens": 60, "stream": False}, timeout=120)
print("E2E mimocode/mimo-auto:", r.status_code)
print(r.text[:400])
