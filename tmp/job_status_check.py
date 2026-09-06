"""Check the current job status of 33033abc (durable ledger) — is it still running?"""
import json
import urllib.request

m = json.loads(open(r"state\secrets\tenant_map.json", encoding="utf-8-sig").read())
key = next(k for k, v in m.items() if v == "tenant_001")
req = urllib.request.Request(
    "http://127.0.0.1:8190/v1/video/jobs/33033abc90764eb8a2c02180e1f0f2ee",
    headers={"Authorization": "Bearer " + key})
with urllib.request.urlopen(req, timeout=15) as r:
    j = json.loads(r.read())
v = j.get("video", j)
print("status:", v.get("status"), "| url:", bool(v.get("url")), "| error:", v.get("error"))
