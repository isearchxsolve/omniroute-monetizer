"""Shallow check: what is HuggingFace's actual state in OmniRoute?"""
import json
import sys
import urllib.request

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from oauth_keepalive import resolve_password  # noqa: E402

BASE = "http://127.0.0.1:20128"
pw = resolve_password()

import http.cookiejar
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with opener.open(r, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}

st, _ = req("POST", "/api/auth/login", {"password": pw})
print("login:", st)

st, data = req("GET", "/api/providers")
print("providers:", st, "total:", data.get("total"))
conns = data.get("connections", [])
for c in conns:
    prov = (c.get("provider") or "").lower()
    name = (c.get("name") or "").lower()
    if "hugging" in prov or "hugging" in name or "hf" == prov:
        key = c.get("apiKey") or ""
        masked = (key[:8] + "..." + key[-4:]) if len(key) > 16 else ("<empty>" if not key else "<short>")
        print(json.dumps({
            "id": c.get("id"),
            "provider": c.get("provider"),
            "name": c.get("name"),
            "authType": c.get("authType"),
            "isActive": c.get("isActive"),
            "apiKey_masked": masked,
            "apiKey_len": len(key),
            "providerSpecificData_keys": list((c.get("providerSpecificData") or {}).keys()),
        }, indent=2))
