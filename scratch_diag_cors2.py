"""scratch_diag_cors2.py — is the API reachable same-origin, and what does the page really call?"""
import json, time, urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def step(n): print(f"[{time.strftime('%H:%M:%S')}] {n}", flush=True)

opts = Options(); opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts); driver.set_script_timeout(40)

target=None
for h in driver.window_handles:
    driver.switch_to.window(h)
    if urllib.parse.urlsplit(driver.current_url).netloc=="app.1min.ai": target=h; break
driver.switch_to.window(target)
step(f"tab {driver.current_url[:55]}")

sess=json.load(open("state/secrets/session_1min_ai.json",encoding="utf-8"))
ex=sess["recorded_exchange"]; url=ex["url"]; body=ex.get("request_body")
path=urllib.parse.urlsplit(url).path
qs=urllib.parse.urlsplit(url).query
same=f"https://app.1min.ai{path}"+(f"?{qs}" if qs else "")
step(f"cross-origin url={url[:60]}")
step(f"same-origin  url={same[:60]}")

JS=r"""
const cb=arguments[arguments.length-1];
(async()=>{ try{
  const r=await fetch(__URL__,{method:__M__,headers:__H__,body:__B__,credentials:'include'});
  let t=''; try{t=(await r.text()).slice(0,200);}catch(e){}
  cb({ok:true,status:r.status,body:t});
}catch(e){cb({ok:false,error:String(e.message||e)});} })();
"""
def fire(label,u,m,h,b):
    js=JS.replace("__URL__",json.dumps(u)).replace("__M__",json.dumps(m)).replace("__H__",json.dumps(h)).replace("__B__",json.dumps(b) if b else "null")
    print(f"   [{label}] -> {json.dumps(driver.execute_async_script(js))[:200]}",flush=True)

hdrs={k:v for k,v in ex.get("request_headers",{}).items()
      if k.lower() in ("content-type","accept","x-auth-token","x-client-platform")}

step("1. same-origin POST with recorded headers")
fire("same-origin", same, ex.get("method","POST"), hdrs, body)

step("2. what origins does the page's own code reference? (scan for api host in window)")
r=driver.execute_script("""
  const out={};
  try{ out.locationOrigin=location.origin; }catch(e){}
  try{ out.hasSW=!!navigator.serviceWorker; }catch(e){}
  return out;
""")
print(f"   -> {json.dumps(r)}", flush=True)
step("DONE")
