"""Wire Google Flow into OmniRoute as a new `googleflow` video connection, then prove a real Veo mp4.

CONTEXT (all measured 2026-08-23):
  - The robot Chrome is signed into Google Labs Flow as isearch.xsolve@gmail.com with 1050 Flow
    credits + 50 free daily -- free Veo 3.1 capacity, no card.
  - Flow's OAuth access token was harvested from the live /fx/api/auth/session and saved (gitignored)
    under state/generated_keys.json['googleflow'].
  - OmniRoute's registry lists `googleflow` (format google-flow, authType oauth, authHeader bearer,
    baseUrl https://aisandbox-pa.googleapis.com, models veo-3.1-generate / veo-3.1-fast-generate /
    veo-3.0-generate) but no connection instance existed.
  - The existing `vertex` connection stores a Google OAuth token (begins `AQ.`) in its `apiKey`
    field with authType apikey, so google-flow follows the same storage convention.

WHAT THIS DOES:
  1. Create a googleflow connection (POST /api/providers) if one does not already exist; otherwise
     update the existing one's token (idempotent -- re-running just refreshes the token).
  2. Read it back and confirm it is active.
  3. Nothing here calls the video endpoint -- proving a real mp4 is a separate, explicit step so the
     token is never spent by accident.

SECRETS: the token is read from the gitignored harvest file, sent once in the create/update body,
and only its length + last 4 chars are ever printed.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
from omniroute_api import OmniRouteAPI, mask_token  # noqa: E402

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
KEYS = ROOT / "state" / "generated_keys.json"

gf = json.loads(KEYS.read_text(encoding="utf-8")).get("googleflow")
if not gf or not gf.get("key"):
    raise SystemExit("no googleflow token in state/generated_keys.json -- run harvest first")
token = gf["key"]
print(f"token to wire: len={len(token)}, ends ...{token[-4:]}  (account {gf.get('email')})")
print(f"token expires: {gf.get('expires')}")
print()

api = OmniRouteAPI()
conns = api.get_connections()
existing = next((c for c in conns if str(c.get("provider")).lower() == "googleflow"), None)

if existing:
    cid = existing["id"]
    print(f"googleflow connection already exists (id={cid}); refreshing its token via PUT")
    res = api.update_connection(cid, {"apiKey": token, "isActive": True})
    print(f"  PUT -> HTTP {res['http_status']}")
else:
    print("no googleflow connection yet; creating one via POST /api/providers")
    payload = {
        "provider": "googleflow",
        "name": "google-flow-labs",
        "apiKey": token,
        "authType": "oauth",
        "isActive": True,
        "priority": 1,
    }
    res = api.create_connection(payload)
    print(f"  POST -> HTTP {res['http_status']}")
    body = res.get("body")
    if isinstance(body, dict):
        # don't print the whole body in case it echoes the token back
        keys = sorted(body.keys())
        print(f"  response keys: {keys}")
        if "error" in body or "message" in body:
            print(f"  server said: {str(body.get('error') or body.get('message'))[:200]}")

# Read back and report
conns = api.get_connections()
gfc = next((c for c in conns if str(c.get("provider")).lower() == "googleflow"), None)
print()
if not gfc:
    print("RESULT: googleflow connection still not present. The create endpoint or body was wrong;")
    print(f"        POST returned HTTP {res.get('http_status')}. See response keys above.")
    sys.exit(2)
print("RESULT: googleflow connection present")
print(f"  id       = {gfc.get('id')}")
print(f"  provider = {gfc.get('provider')}")
print(f"  name     = {gfc.get('name')}")
print(f"  authType = {gfc.get('authType')}")
print(f"  isActive = {gfc.get('isActive')}")
print(f"  apiKey   = {mask_token(str(gfc.get('apiKey') or ''))}")
print(f"  status   = {gfc.get('testStatus')}")
print("\nnext: POST /v1/videos/generations model=googleflow/veo-3.0-generate with timeout_ms, then")
print("      verify bytes[4:8]==b'ftyp'. Nothing counts until a real mp4 lands.")
