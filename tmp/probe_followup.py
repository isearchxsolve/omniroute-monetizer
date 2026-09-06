"""Read-only follow-up: orcarouter 401 detail; ainative full model list dump."""
import json
import pathlib
import sys

import requests

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI  # noqa: E402

c = OmniRouteAPI()
c.login()
conns = {x.get("provider"): x for x in c.get_connections()}

# orcarouter: show the 401 body shape (redacted) to learn auth requirements
key = conns["orcarouter"].get("apiKey")
r = requests.get(
    "https://api.orcarouter.ai/v1/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=30,
)
print("orcarouter /v1/models HTTP", r.status_code, "body head:", r.text[:300])
r2 = requests.get("https://api.orcarouter.ai/v1/models", timeout=30)
print("orcarouter no-auth HTTP", r2.status_code, "body head:", r2.text[:300])

# ainative: dump all 94 ids (names only, safe)
key = conns["ainative"].get("apiKey")
r = requests.get(
    "https://api.ainative.studio/api/v1/models",
    headers={"Authorization": f"Bearer {key}"},
    timeout=30,
)
body = r.json()
items = body.get("data") if isinstance(body, dict) else body
ids = [m.get("id") if isinstance(m, dict) else str(m) for m in (items or [])]
print("ainative", r.status_code, "all ids:")
for i in ids:
    print(" ", i)
