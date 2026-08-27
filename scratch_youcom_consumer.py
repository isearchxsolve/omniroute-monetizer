# -*- coding: utf-8 -*-
"""you.com: quick shallow probe for a FREE consumer chat surface (not the paid API playground)."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(60)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            break
    except Exception:
        continue
else:
    raise SystemExit("NO you.com tab")

# Probe consumer surfaces
for url in ["https://you.com/search", "https://you.com/chat", "https://you.com/"]:
    try:
        d.get(url)
        time.sleep(4)
        print(f"\n=== {url} ===")
        print("final url:", d.current_url)
        # Is there a chat input (free consumer chat)?
        probe = d.execute_script(r"""
        return (function(){
          function visible(el){
            const r=el.getBoundingClientRect();
            if(r.width<=0||r.height<=0) return false;
            const st=getComputedStyle(el);
            return st.display!=='none'&&st.visibility!=='hidden';
          }
          const tas=Array.from(document.querySelectorAll('textarea,[contenteditable="true"]')).filter(visible);
          const body=(document.body.innerText||'');
          return {
            inputs: tas.map(t=>({tag:t.tagName, ph:t.placeholder||'', id:(t.id||'').slice(0,30)})),
            hasPaywall:/upgrade|premium|subscribe|sign in|log in|paywall|limit reached/i.test(body),
            bodyHead: body.replace(/\n/g,' | ').slice(0,200)
          };
        })()
        """)
        print(json.dumps(probe, indent=1)[:800])
        if probe.get("inputs"):
            print(f">>> FREE CHAT INPUT FOUND at {url}")
    except Exception as e:
        print(f"  {url} failed: {e}")
