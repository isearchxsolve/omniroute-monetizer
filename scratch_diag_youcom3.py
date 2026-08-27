# -*- coding: utf-8 -*-
"""you.com probe v3: many SMALL execute_script calls to isolate the null problem."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(30)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            break
    except Exception:
        continue
else:
    raise SystemExit("NO you.com tab")

print("URL:", d.current_url[:110])

def probe(name, script):
    try:
        r = d.execute_script("return " + script)
        print(f"{name}: {json.dumps(r)[:300]}")
    except Exception as e:
        print(f"{name}: EXC {str(e)[:150]}")

probe("bodyLen", "(document.body? (document.body.innerText||'').length : -1)")
probe("nTextareas", "document.querySelectorAll('textarea').length")
probe("nCE", "document.querySelectorAll('[contenteditable]').length")
probe("nButtons", "document.querySelectorAll('button').length")
probe("nIframes", "document.querySelectorAll('iframe').length")
probe("iframeSrcs", "Array.from(document.querySelectorAll('iframe')).map(f=>(f.src||'').slice(0,90))")
probe("bodyHead", "(document.body? (document.body.innerText||'').slice(0,400) : 'NO BODY')")
probe("taDetails", "Array.from(document.querySelectorAll('textarea')).map(el=>({id:el.id, ph:el.placeholder||'', vis:(el.getBoundingClientRect().width>0)}))")
probe("btnDetails", "Array.from(document.querySelectorAll('button')).slice(0,15).map(el=>({al:el.getAttribute('aria-label')||'', dt:el.getAttribute('data-testid')||'', dis:el.disabled}))")
