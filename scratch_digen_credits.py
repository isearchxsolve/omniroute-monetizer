# -*- coding: utf-8 -*-
"""Read-only digen credit/quota check via the captured scene_info endpoint.
Authenticates the token and reports any balance/quota fields WITHOUT spending a credit.
"""
import json, pathlib, requests

raw = json.loads(pathlib.Path("state/secrets/session_digen_ai.json").read_text(encoding="utf-8"))
exchanges = raw["recorded_job"].get("exchanges", [])
_DROP = {"content-length", "accept-encoding", "cookie"}
headers = {}
submit_body = None
for ex in exchanges:
    h = ex.get("request_headers", {})
    if "Digen-Token" in h and not headers:
        for k, v in h.items():
            if not k.startswith(":") and k.lower() not in _DROP:
                headers[k] = v
    if "scene_info" in ex.get("url", "") and ex.get("method") == "POST":
        submit_body = ex.get("request_body")
headers["accept-encoding"] = "gzip, deflate"

print("scene_info request body (captured):", (submit_body or "")[:200])
try:
    body = json.loads(submit_body) if submit_body else {}
except Exception:
    body = {}
r = requests.post("https://api.digen.ai/v1/user/scene_info", headers=headers,
                  json=body, timeout=20)
print("scene_info status:", r.status_code)
try:
    j = r.json()
    print("errCode:", j.get("errCode"), "errMsg:", j.get("errMsg"))
    data = j.get("data") or {}
    # print any field that looks like credit/quota/balance/count
    def walk(o, prefix=""):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = k.lower()
                if any(w in kl for w in ("credit", "quota", "balance", "count", "remain", "limit", "free", "coin", "point", "num")):
                    print("  ", prefix + k, "=", v)
                if isinstance(v, (dict, list)):
                    walk(v, prefix + k + ".")
        elif isinstance(o, list):
            for i, v in enumerate(o[:3]):
                walk(v, prefix + "[%d]." % i)
    walk(data)
    print("data top keys:", list(data.keys()) if isinstance(data, dict) else type(data))
except Exception as e:
    print("non-JSON:", e, r.text[:200])
