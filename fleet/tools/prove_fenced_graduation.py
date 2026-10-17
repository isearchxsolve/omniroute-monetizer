"""Fresh Kaggle browser/curl proof through generation-fenced production queue."""
import base64, hashlib, json, time
from pathlib import Path
from door_client import request
OUT=Path(__file__).resolve().parents[2]/"state/fenced_graduation_live_20261017.json"
if OUT.exists():
    data=json.loads(OUT.read_text(encoding="utf-8"))
else:
    data={"capture_id":f"github.cpython.repair.{int(time.time())}.v1"}

def save():OUT.write_text(json.dumps(data,indent=2),encoding="utf-8")
def wait_for(label):
    jid=data[label+"_submission"]["job_id"]
    for _ in range(60):
        job=request("/v1/tools/web.result",params={"job_id":jid})
        data[label+"_result"]=job;save()
        print(label,job.get("status"),flush=True)
        if job.get("status") in ("done","failed"):
            if job["status"]!="done":raise RuntimeError(label+" actual job failed: "+str(job.get("error")))
            body=base64.b64decode(job["content_b64"])
            value=json.loads(body)
            if label=="cold":
                assert job["executed_by"]=="kaggle:playwright"
                assert value["final_url"]=="https://api.github.com/repos/python/cpython"
                assert json.loads(value["text"])["full_name"]=="python/cpython"
            else:
                assert job["executed_by"]=="kaggle:cloud-cell"
                assert value["full_name"]=="python/cpython"
            data[label+"_proof"]={"verified":True,"http_status":job["http_status"],"bytes":len(body),
                "body_sha256":hashlib.sha256(body).hexdigest(),"executor":job["executed_by"],
                "generation":job["spec"]["_queue_generation"]}
            save();return
        time.sleep(5)
    raise TimeoutError(label+" not completed; actual receipt preserved")
if "cold_submission" not in data:
    data["cold_submission"]=request("/v1/tools/web.execute",{"url":"https://api.github.com/repos/python/cpython",
        "capture_id":data["capture_id"],"timeout_s":30});save()
wait_for("cold")
# Job completion is strongly consistent; the legacy capture KV publication can
# become visible later. Require the real pin, allowing bounded propagation.
for _ in range(18):
    data["capture_status"]=request("/v1/captures/status",params={"capture_id":data["capture_id"]});save()
    if data["capture_status"].get("execution_pin")=="wire_verified":break
    time.sleep(5)
assert data["capture_status"].get("execution_pin")=="wire_verified"
if "warm_submission" not in data:
    data["warm_submission"]=request("/v1/tools/web.execute",{"capture_id":data["capture_id"],"timeout_s":30});save()
wait_for("warm")
data["all_verified"]=True;save()
print("REAL_FENCED_BROWSER_AND_CURL_PROOF",str(OUT),flush=True)
