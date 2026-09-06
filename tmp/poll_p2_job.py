"""Poll the P2 consumer-proof video job on :8190 until terminal (read-only)."""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")

JOB_ID = sys.argv[1] if len(sys.argv) > 1 else "3f79c907d36641d1a89d017dc4cc75b2"
MAX_WAIT = int(sys.argv[2]) if len(sys.argv) > 2 else 3600

key = next(v for v in [None])  # placeholder, replaced below
m = json.loads(open(r"state\secrets\tenant_map.json", encoding="utf-8-sig").read())
key = next(k for k, v in m.items() if v == "tenant_001")

deadline = time.time() + MAX_WAIT
last = None
while time.time() < deadline:
    req = urllib.request.Request(
        f"http://127.0.0.1:8190/v1/video/jobs/{JOB_ID}",
        headers={"Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read())
    v = j.get("video", j)
    sig = (v.get("status"), v.get("progress"), v.get("error"))
    if sig != last:
        print(f"[{time.strftime('%H:%M:%S')}] status={v.get('status')} "
              f"progress={v.get('progress')} error={v.get('error')}", flush=True)
        last = sig
    if v.get("status") in ("succeeded", "failed", "cancelled"):
        print(json.dumps({k: v.get(k) for k in ("status", "url", "error", "creditsSpent")},
                         indent=2))
        break
    time.sleep(30)
else:
    print("POLL_TIMEOUT")
