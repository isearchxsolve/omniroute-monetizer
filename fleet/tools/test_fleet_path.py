import json
import subprocess
import time
import base64

DOOR = "https://omniroute-relay.omniroute-fleet-kd.workers.dev"

def curl_json(args):
    cmd = ["curl", "-s", "--max-time", "30"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    return json.loads(r.stdout)

# Fleet path: POST method -> not simple -> queued to Kaggle
r = curl_json(["-X", "POST", f"{DOOR}/v1/tools/web.execute?token=GOLD24",
               "-H", "content-type: application/json",
               "-d", json.dumps({
                   "mode": "fleet",
                   "url": "https://httpbin.org/post",
                   "method": "POST",
                   "headers": {"User-Agent": "omniroute-agent-fleet", "X-Fleet-Test": "kaggle-executor"},
                   "body": json.dumps({"hello": "from the agent internet", "via": "kaggle-cloud-cell"}),
                   "timeout_s": 30
               })])
print("FLEET SUBMIT:", json.dumps(r))
jid = r.get("job_id")
if not jid:
    raise SystemExit("no job_id — submit failed")

# Poll for result (fleet kernel boots ~3-5 min on fresh push)
print("\nPolling for fleet result (this can take several minutes on kernel boot)...")
deadline = time.time() + 420
final = None
while time.time() < deadline:
    time.sleep(15)
    res = curl_json([f"{DOOR}/v1/tools/web.result?token=GOLD24&job_id={jid}"])
    status = res.get("status")
    print(f"  [{time.strftime('%H:%M:%S')}] status = {status}")
    if status in ("done", "failed"):
        final = res
        break

if not final:
    raise SystemExit("TIMEOUT waiting for fleet result")

print("\nFLEET RESULT:")
print("  status:", final.get("status"))
print("  http_status:", final.get("http_status"))
print("  executed_by:", final.get("executed_by"))
print("  duration_ms:", final.get("duration_ms"))
if final.get("content_b64"):
    body = base64.b64decode(final["content_b64"]).decode("utf-8", "replace")
    try:
        echo = json.loads(body)
        print("  echoed headers X-Fleet-Test:", echo.get("headers", {}).get("X-Fleet-Test"))
        print("  echoed data:", echo.get("data", "")[:120])
        print("  origin IP:", echo.get("origin"))
    except Exception:
        print("  raw:", body[:200])

print("\nFLEET PATH VERIFIED" if final.get("status") == "done" else "\nFLEET PATH FAILED")
