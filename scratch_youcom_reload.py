# -*- coding: utf-8 -*-
"""you.com reload test: does loading the page WITH ?query= auto-run it? Also capture any
error/loading state in the response panel and check for a network error toast."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(90)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            break
    except Exception:
        continue
else:
    raise SystemExit("NO you.com tab")

QUERY = "What is the capital of France? Reply with just the city name."
import urllib.parse
url = "https://you.com/platform/playground/answer?query=" + urllib.parse.quote(QUERY)
print("Navigating to:", url[:100])
d.get(url)

# wait for load
for _ in range(30):
    if d.execute_script("return document.readyState") == "complete":
        break
    time.sleep(0.5)
print("readyState complete")

def get_response_json():
    return d.execute_script(r"""
    return (function(){
      const blocks = Array.from(document.querySelectorAll('.language-json'))
        .map(el=>(el.innerText||'').trim()).filter(Boolean);
      for(const b of blocks){ if(b.includes('"answer"')) return b; }
      return null;
    })()
    """)

def panel_state():
    return d.execute_script(r"""
    return (function(){
      // find the Response section and any loading/error indicators
      const body = document.body.innerText||'';
      const hasLoading = /loading|generating|thinking/i.test(body);
      const hasError = /error|failed|rate limit|quota|exceeded|unauthorized|401|403|429/i.test(body);
      // grab text near 'Response' heading
      const idx = body.indexOf('Response');
      const near = idx>=0? body.slice(idx, idx+300) : '(no Response heading)';
      return {hasLoading, hasError, nearResponse: near.replace(/\s+/g,' ').slice(0,250)};
    })()
    """)

t0 = time.time()
for i in range(30):
    time.sleep(2)
    cur = get_response_json()
    st = panel_state()
    el = time.time()-t0
    if cur:
        try:
            ans = json.loads(cur).get("answer","")
            print(f"t={el:.0f}s RESPONSE JSON present. answer head: {ans[:120]}")
            if "paris" in ans.lower() or "France" in ans:
                print(">>> MATCHES OUR QUERY — reload auto-runs!")
            else:
                print(">>> does NOT match our query (stale?)")
            break
        except Exception:
            print(f"t={el:.0f}s json block present but unparseable")
            break
    else:
        print(f"t={el:.0f}s no response json | loading={st['hasLoading']} error={st['hasError']} | near: {st['nearResponse'][:120]}")
else:
    print("TIMEOUT waiting for response after reload")
    st = panel_state()
    print("final panel state:", json.dumps(st, indent=2))
