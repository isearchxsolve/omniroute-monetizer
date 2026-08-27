import json, sys, pathlib, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from curl_cffi.requests import Session as CC

p = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_v0_app.json")
d = json.loads(p.read_text(encoding="utf-8-sig"))
rx = d["recorded_exchange"]
url = rx["url"]
body = rx["request_body"]
hdrs = {k: v for k, v in rx.get("request_headers", {}).items() if not k.startswith(":")}
hdrs.pop("content-length", None); hdrs.pop("Content-Length", None)
hdrs["cookie"] = d.get("cookie_header", "")

# inject a fresh prompt (replace sentinel) so we don't re-send the captured one
SENT = "Reply exactly one word: Omni."
new_prompt = "Reply exactly one word: Lighthouse."
new_body = body.replace(SENT, new_prompt)
print("injected?", new_body != body)

s = CC(impersonate="chrome")
r = s.post(url, data=new_body.encode(), headers=hdrs, timeout=60)
print("status:", r.status_code)
print("resp headers:", {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "transfer-encoding")})
print("body repr:", repr(r.text[:400]))
print("body len:", len(r.text))
