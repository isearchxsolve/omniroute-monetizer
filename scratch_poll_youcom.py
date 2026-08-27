# -*- coding: utf-8 -*-
"""you.com poll: wait for the Response panel to populate after Run query."""
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

for i in range(15):
    r = d.execute_script(r"""
    return (function(){
      const json = Array.from(document.querySelectorAll('.language-json,pre'))
        .map(el=>(el.innerText||'')).filter(t=>t.trim() && !t.includes('Run a query to see'));
      return {bodyLen:(document.body.innerText||'').length,
              jsonBlocks: json.map(t=>t.slice(0,300)),
              tail:(document.body.innerText||'').slice(-300)};
    })()
    """)
    print(f"t={i*2}s bodyLen={r['bodyLen']} jsonBlocks={len(r['jsonBlocks'])}")
    if r["jsonBlocks"]:
        print("FOUND RESPONSE:")
        print(json.dumps(r["jsonBlocks"], indent=2)[:1500])
        break
    time.sleep(2)
else:
    print("TIMEOUT — tail:", r["tail"][:400])
