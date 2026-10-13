import json
import subprocess
import time
import base64

DOOR = "https://omniroute-relay.omniroute-fleet-kd.workers.dev"

def curl_json(args):
    cmd = ["curl", "-s", "--max-time", "30"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
    return json.loads(r.stdout)

# 1. Health - expect version 2
h = curl_json([f"{DOOR}/health?token=GOLD24"])
print("HEALTH:", json.dumps(h))

# 2. Edge fast path: fetch a public JSON API through the tool
r = curl_json(["-X", "POST", f"{DOOR}/v1/tools/web.execute?token=GOLD24",
               "-H", "content-type: application/json",
               "-d", json.dumps({
                   "url": "https://api.github.com/zen",
                   "method": "GET",
                   "headers": {"User-Agent": "omniroute-agent"},
                   "timeout_s": 15
               })])
print("\nEDGE EXECUTE:")
print("  job_id:", r.get("job_id"))
print("  status:", r.get("status"))
print("  http_status:", r.get("http_status"))
print("  executed_by:", r.get("executed_by"))
print("  duration_ms:", r.get("duration_ms"))
if r.get("result", {}).get("content_b64"):
    content = base64.b64decode(r["result"]["content_b64"]).decode("utf-8", "replace")
    print("  CONTENT:", content[:200])

# 3. Result lookup by job_id
if r.get("job_id"):
    res = curl_json([f"{DOOR}/v1/tools/web.result?token=GOLD24&job_id={r['job_id']}"])
    print("\nRESULT LOOKUP: status =", res.get("status"), "| http =", res.get("http_status"))

print("\nEDGE PATH VERIFIED" if r.get("status") == "done" else "\nEDGE PATH FAILED")
