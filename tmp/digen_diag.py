"""Read-only: dump the digen submit template's scene_params, classify errCode 4002."""
import json
import pathlib
import sys

d = json.loads(pathlib.Path(
    r"D:\omniroute-monetizer\state\secrets\session_digen_ai.json").read_text(encoding="utf-8"))
exs = d["recorded_job"]["exchanges"]
submit = [e for e in exs if "submit" in (e.get("url") or "") and e.get("request_body")][0]
body = json.loads(submit["request_body"])
sp = json.loads(body["scene_params"])
print("model:", body.get("model"))
print("scene_id:", body.get("scene_id"))
for k in sorted(sp):
    v = str(sp[k])
    if v and v not in ('""', "0"):
        print("  ", k, "=", v[:70])

# errCode taxonomy probe: hit scene_info POST (captured 200 earlier) with same headers
hdrs = None
for e in exs:
    h = e.get("request_headers") or {}
    if "Digen-Token" in h:
        hdrs = {k: v for k, v in h.items() if not k.startswith(":")}
        break
h2 = {k: v for k, v in hdrs.items() if k.lower() != "content-length"}
r = requests.post("https://api.digen.ai/v1/user/scene_info", headers=h2, json={}, timeout=20)
print("scene_info replay HTTP", r.status_code, r.text[:200])
