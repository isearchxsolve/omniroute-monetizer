import json, sys
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient
from curl_cffi.requests import Session as CCSession

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")
c = UniversalSessionClient(str(SEATDIR / "session_cerebras_inference_chat.json"))
s = CCSession(impersonate="chrome")

# Extract CSRF token from the cookie jar
csrf_cookie = None
for part in c.headers.get("cookie", "").split(";"):
    part = part.strip()
    if part.startswith("__Host-authjs.csrf-token="):
        csrf_cookie = part.split("=", 1)[1]
        break
print("csrf cookie:", repr(csrf_cookie[:60]) if csrf_cookie else None)
# NextAuth csrf cookie = "<token>%<hash>"; header needs the token part
csrf_token = csrf_cookie.split("%")[0] if csrf_cookie else None
print("csrf token:", repr(csrf_token[:60]) if csrf_token else None)

body = {"messages":[{"role":"user","content":"Reply exactly one word: Omni."}],
        "model":"gemma-4-31b","stream":False,"temperature":0.7,"top_p":0.9}

hdrs = dict(c.headers)
if csrf_token:
    hdrs["x-csrf-token"] = csrf_token
r = s.request("POST", c.url, headers=hdrs, data=json.dumps(body).encode(), timeout=60)
print(f"with x-csrf-token: status={r.status_code} body[:300]={r.text[:300]!r}")
