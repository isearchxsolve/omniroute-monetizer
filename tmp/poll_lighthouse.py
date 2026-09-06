"""Read-only: check the running lighthouse job and both tabs; wait to terminal."""
import json
import time
import urllib.request

JOB = "33033abc90764eb8a2c02180e1f0f2ee"
m = json.loads(open(r"state\secrets\tenant_map.json", encoding="utf-8-sig").read())
key = next(k for k, v in m.items() if v == "tenant_001")

deadline = time.time() + 2700
last = None
while time.time() < deadline:
    req = urllib.request.Request(
        f"http://127.0.0.1:8190/v1/video/jobs/{JOB}",
        headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    v = j.get("video", j)
    sig = (v.get("status"), bool(v.get("url")), v.get("error"))
    if sig != last:
        print(f"[{time.strftime('%H:%M:%S')}] status={v.get('status')} url={bool(v.get('url'))} "
              f"error={v.get('error')}", flush=True)
        last = sig
    if v.get("status") in ("succeeded", "failed", "cancelled"):
        print(json.dumps({k: v.get(k) for k in ("status", "url", "session", "error")},
                         indent=2))
        break
    time.sleep(30)
else:
    print("STILL_RUNNING after 45min wait window")
