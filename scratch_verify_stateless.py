import json, time, urllib.request
BASE = "http://127.0.0.1:8190"
job_key = f"verify-stateless-{int(time.time())}"
body = json.dumps({
    "model": "video/auto",
    "messages": [{"role": "user", "content": "A slow pan across a neon-lit alley at night."}],
    "video": {"job_key": job_key},
}).encode()
req = urllib.request.Request(BASE + "/v1/chat/completions", data=body, method="POST")
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(req, timeout=20) as r:
    rec = json.loads(r.read().decode())
    print("HTTP", r.status)
v = rec.get("video", {})
print("submit status:", v.get("status"))
print("ROUTED TO provider:", v.get("provider"), "| session:", v.get("session"))
print("jobId:", v.get("jobId"))
print("job_key:", job_key)
