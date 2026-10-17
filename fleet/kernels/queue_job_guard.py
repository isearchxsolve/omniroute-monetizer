"""Atomically claim the current durable generation before executing queue work."""

def claim_queue_job(order_text, prefix, door, token):
    import json
    import urllib.request
    import urllib.parse
    spec = json.loads(order_text.split(prefix, 1)[1])
    job_id = spec.get("job_id")
    if not job_id:
        return {"claimed": False, "reason": "missing_job_id"}
    query = urllib.parse.urlencode({"token": token})
    payload = {"job_id": job_id, "generation": spec.get("_queue_generation", 0),
               "executor": "playwright" if prefix == "PW_EXECUTE:" else "fleet"}
    request = urllib.request.Request(door + "/v1/tools/web.claim?" + query,
        data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json", "User-Agent":"omniroute-kaggle-worker"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read(200000).decode("utf-8"))
