"""Two cheap fixes:
1. gemini: randomize _reqid + pull fresh at from page, rebuild URL, replay.
2. cerebras: probe alternate endpoints to find the real chat path.
"""
import json, sys, time, random, urllib.parse
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from universal_replay import UniversalSessionClient
from cdp import Page
from curl_cffi.requests import Session as CCSession

SEATDIR = Path(r"d:\omniroute-monetizer\state\secrets")

# ---------- GEMINI: fresh at + random _reqid ----------
print("=== GEMINI fresh-at + random _reqid ===")
with Page("gemini.google.com", port=9222) as p:
    at = p.evaluate("(window.WIZ_global_data && window.WIZ_global_data.SNlM0e) || null")
    fsid = p.evaluate("(window.WIZ_global_data && window.WIZ_global_data.FdrFJe) || null")
    bl = p.evaluate("(window.WIZ_global_data && window.WIZ_global_data.cfb2h) || null")
print("fresh at:", repr(at[:30]) if at else None, "fsid:", fsid, "bl:", bl)

g = UniversalSessionClient(str(SEATDIR / "session_google_gemini_web.json"))
url = g.url
# rebuild query with fresh f.sid, random _reqid, current bl
q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
if fsid: q["f.sid"] = str(fsid)
if bl: q["bl"] = str(bl)
q["_reqid"] = str(random.randint(100000, 9999999))
q["rt"] = "c"
base = urllib.parse.urlparse(url)._replace(query=urllib.parse.urlencode(q)).geturl()
print("rebuilt url:", base[:140])

# rebuild body with fresh at
body = g.base_body
fields = urllib.parse.parse_qs(body, keep_blank_values=True)
if at and "at" in fields:
    fields["at"] = [at]
new_body = urllib.parse.urlencode({k: v[0] for k, v in fields.items()})
# inject a real prompt
new_body = new_body.replace(urllib.parse.quote("Reply exactly one word: Omni."),
                            urllib.parse.quote("What is 2+2? Answer with just the number."))

hdrs = dict(g.headers)
s = CCSession(impersonate="chrome")
r = s.request("POST", base, headers=hdrs, data=new_body.encode(), timeout=60)
print(f"gemini status={r.status_code} body[:200]={r.text[:200]!r}")

# ---------- CEREBRAS: probe endpoints ----------
print("\n=== CEREBRAS endpoint probe ===")
c = UniversalSessionClient(str(SEATDIR / "session_cerebras_inference_chat.json"))
cs = CCSession(impersonate="chrome")
body = {"messages":[{"role":"user","content":"Reply exactly one word: Omni."}],
        "model":"gemma-4-31b","stream":False}
for path in ["/api/chat/completions", "/api/chat", "/api/completions",
             "/api/inference/chat", "/v1/chat/completions"]:
    u = "https://chat.cerebras.ai" + path
    rr = cs.request("POST", u, headers=c.headers, data=json.dumps(body).encode(), timeout=30)
    print(f"  {path:28s} -> {rr.status_code} {rr.text[:80]!r}")
