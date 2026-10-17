"""Real Worker claim contention with real upstream bytes; no simulated responses."""
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import requests

DOOR = os.environ.get("OMNIROUTE_DOOR", "http://127.0.0.1:8792")
TOKEN = os.environ.get("OMNIROUTE_TOKEN", "GOLD24")
TARGET = "https://api.github.com/repos/python/cpython"
OUT = Path(__file__).resolve().parents[2] / "state/fenced_queue_live_wire_20261017.json"

def call(path, payload=None, **params):
    response = requests.request("POST" if payload is not None else "GET", DOOR+path,
        params={"token": TOKEN, **params}, json=payload, timeout=35)
    return response.status_code, response.json()

status, submitted = call("/v1/tools/web.execute", {"url":TARGET,"mode":"fleet","timeout_s":30})
assert status == 200, (status, submitted)
jid = submitted["job_id"]
_, job = call("/v1/tools/web.result", job_id=jid)
generation = job["spec"]["_queue_generation"]
wrong_status, wrong = call("/v1/tools/web.claim", {"job_id":jid,"generation":generation,"executor":"playwright"})
assert wrong_status == 200 and not wrong["claimed"]

def claim(_):
    return call("/v1/tools/web.claim", {"job_id":jid,"generation":generation,"executor":"fleet"})
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    answers = list(executor.map(claim, range(4)))
winners = [body for status, body in answers if status == 200 and body.get("claimed")]
assert len(winners) == 1, "exclusive claim was not earned"
spec = winners[0]["spec"]
wire = requests.get(spec["url"], timeout=25)
wire.raise_for_status()
assert wire.json()["full_name"] == "python/cpython"
payload = {"job_id":jid,"status":"done","http_status":wire.status_code,
    "content_type":wire.headers["content-type"],"content_b64":base64.b64encode(wire.content).decode(),
    "executed_by":"repair-audit:real-http-client","_queue_generation":generation,"_lease_token":spec["_lease_token"]}
status, accepted = call("/v1/tools/web.result", payload)
assert status == 200 and accepted.get("stored"), (status,accepted)
_, final = call("/v1/tools/web.result", job_id=jid)
assert "lease" not in final
assert hashlib.sha256(base64.b64decode(final["content_b64"])).digest() == hashlib.sha256(wire.content).digest()
stale_status, stale = call("/v1/tools/web.result", payload)
assert stale_status == 409
receipt = {"scope":"actual Worker runtime, four concurrent claims, real GitHub HTTP bytes; not a Kaggle render",
    "job_id":jid,"claim_attempts":4,"claims_granted":len(winners),"wrong_executor_rejected":not wrong["claimed"],
    "upstream_status":wire.status_code,"upstream_bytes":len(wire.content),"body_sha256":hashlib.sha256(wire.content).hexdigest(),
    "completed_status":final["status"],"stale_result_http_status":stale_status,
    "lease_token_hidden_from_result":True}
OUT.write_text(json.dumps(receipt,indent=2),encoding="utf-8")
print(json.dumps(receipt,indent=2))
