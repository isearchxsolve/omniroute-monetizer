"""scratch_diag_cors.py — why do API-origin replays 'Failed to fetch' from the app tab?

For 1min.ai: fire fetches from the app.1min.ai tab to api.1min.ai with progressively
simpler header sets, and also capture the preflight outcome via a HEAD/GET probe.
"""
import json, time, urllib.parse, urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def step(n):
    print(f"[{time.strftime('%H:%M:%S')}] {n}", flush=True)

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(40)

# find the app.1min.ai tab
target = None
for h in driver.window_handles:
    driver.switch_to.window(h)
    if urllib.parse.urlsplit(driver.current_url).netloc == "app.1min.ai":
        target = h
        break
if not target:
    print("no app.1min.ai tab"); raise SystemExit(1)
driver.switch_to.window(target)
step(f"on tab {driver.current_url[:60]}")

sess = json.load(open("state/secrets/session_1min_ai.json", encoding="utf-8"))
ex = sess["recorded_exchange"]
url = ex["url"]
body = ex.get("request_body")
hdrs = ex.get("request_headers", {})
step(f"url={url[:70]}")

FORBID = {"accept-charset","accept-encoding","access-control-request-headers","access-control-request-method",
 "connection","content-length","cookie","cookie2","date","dnt","expect","feature-policy","host",
 "keep-alive","origin","referer","te","trailer","transfer-encoding","upgrade","via"}
def clean(h):
    return {k:v for k,v in h.items() if k.lower() not in FORBID
            and not k.lower().startswith("sec-") and not k.lower().startswith("proxy-")}

JS = r"""
const cb = arguments[arguments.length-1];
(async () => {
  try {
    const r = await fetch(__URL__, { method:__METHOD__, headers:__HDRS__, body:__BODY__,
      credentials:'include', redirect:'follow' });
    let t=''; try { t = (await r.text()).slice(0,300); } catch(e){}
    cb({ ok:true, status:r.status, type:r.headers.get('content-type'), body:t });
  } catch(e) { cb({ ok:false, error:String(e && e.message ? e.message : e), name:e && e.name }); }
})();
"""
def fire(label, headers, use_body=True):
    js = JS.replace("__URL__", json.dumps(url)).replace("__METHOD__", json.dumps(ex.get("method","POST")))
    js = js.replace("__HDRS__", json.dumps(headers))
    js = js.replace("__BODY__", json.dumps(body) if (use_body and body) else "null")
    r = driver.execute_async_script(js)
    print(f"   [{label}] -> {json.dumps(r)[:220]}", flush=True)
    return r

step("A. full recorded headers (minus forbidden)")
fire("full", clean(hdrs))

step("B. only content-type + accept")
fire("ct+accept", {"content-type": hdrs.get("Content-Type") or hdrs.get("content-type") or "application/json",
                   "accept": hdrs.get("accept","application/json")})

step("C. content-type + accept + X-Auth-Token")
h = {"content-type": hdrs.get("Content-Type") or hdrs.get("content-type") or "application/json",
     "accept": hdrs.get("accept","application/json")}
tok = hdrs.get("X-Auth-Token") or hdrs.get("x-auth-token")
if tok: h["X-Auth-Token"] = tok
fire("ct+accept+token", h)

step("D. GET probe to API root (no custom headers) — tests basic CORS reachability")
js = JS.replace("__URL__", json.dumps("https://api.1min.ai/")).replace("__METHOD__", '"GET"')
js = js.replace("__HDRS__", "{}").replace("__BODY__", "null")
r = driver.execute_async_script(js)
print(f"   [GET root] -> {json.dumps(r)[:220]}", flush=True)

step("DONE")
