# -*- coding: utf-8 -*-
"""Focused felo test: fire EXACT recorded body (unmodified) via script args.

If the exact bytes still 422 with 'input is a string', the transport is double-encoding.
We then try passing the body as a JS object (parsed) and letting fetch stringify it.
"""
import json
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(90)

sess = json.load(open(r"d:\omniroute-monetizer\state\secrets\session_felo_ai_web.json", encoding="utf-8"))
rx = sess["recorded_exchange"]
url, method = rx["url"], rx.get("method", "POST")
headers = {k: v for k, v in (rx.get("request_headers") or {}).items()
           if k.lower() not in {"host", "content-length", "connection", "accept-encoding",
                                "cookie", "origin", "user-agent", "sec-fetch-site",
                                "sec-fetch-mode", "sec-fetch-dest", "sec-ch-ua",
                                "sec-ch-ua-mobile", "sec-ch-ua-platform"}}
body_str = rx.get("request_body") or ""

# focus felo tab
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if driver.current_url.startswith("https://felo.ai"):
            break
    except Exception:
        continue
print("on:", driver.current_url)

# TEST A: body as string argument
js = r"""
const url=arguments[0], method=arguments[1], headers=arguments[2], body=arguments[3], cb=arguments[4];
fetch(url,{method,headers,body,credentials:'include'})
 .then(async r=>cb({status:r.status, body:(await r.text()).slice(0,800)}))
 .catch(e=>cb({error:String(e)}));
"""
resA = driver.execute_async_script(js, url, method, headers, body_str)
print("TEST A (string body):", resA.get("status"), resA.get("error", ""))
print("  body:", resA.get("body", "")[:300])

# TEST B: body as parsed object, let fetch JSON-stringify via JSON.stringify in JS
body_obj = json.loads(body_str)
jsB = r"""
const url=arguments[0], method=arguments[1], headers=arguments[2], bodyObj=arguments[3], cb=arguments[4];
fetch(url,{method,headers,body:JSON.stringify(bodyObj),credentials:'include'})
 .then(async r=>cb({status:r.status, body:(await r.text()).slice(0,800)}))
 .catch(e=>cb({error:String(e)}));
"""
resB = driver.execute_async_script(jsB, url, method, headers, body_obj)
print("TEST B (object -> JSON.stringify):", resB.get("status"), resB.get("error", ""))
print("  body:", resB.get("body", "")[:300])
