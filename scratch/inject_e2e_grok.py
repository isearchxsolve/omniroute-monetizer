"""Inject fresh grok cookie header into grok-web connection and E2E test."""
import sys, json
sys.path.insert(0, "scripts/automation")
from pathlib import Path
from omniroute_api import OmniRouteAPI

ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "state" / "generated_keys.json"
data = json.loads(KEYS.read_text(encoding="utf-8"))
entry = data["cookie_header:grok-web"]
header = entry["cookie_header"]
print("cookie names:", entry["cookie_names"])
print("strong:", entry["strong"])

api = OmniRouteAPI()
api.login()

CID = "142fea8e-eacf-4ce3-b042-fc3af37cb36c"
r = api.update_connection(CID, {"apiKey": header})
print("update:", r.get("http_status"))

t = api.test_connection(CID)
print("test:", t.get("http_status"), json.dumps(t.get("result"))[:250])

# E2E
payload = {
    "model": "grok-web/fast",
    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
    "max_tokens": 60,
    "stream": False,
}
resp = api.session.post(f"{api.v1}/chat/completions", json=payload, timeout=120)
print("E2E HTTP:", resp.status_code)
print("body:", resp.text[:400])
if resp.status_code == 200:
    try:
        j = resp.json()
        print("CONTENT:", repr(j["choices"][0]["message"]["content"][:200]))
    except Exception as e:
        print("parse err:", e)
