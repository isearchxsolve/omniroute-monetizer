# -*- coding: utf-8 -*-
"""Diagnose the you.com tab: what inputs and message containers exist, is it interactive?"""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(30)

target = None
for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            target = d.current_url
            break
    except Exception:
        continue

if not target:
    print("NO you.com tab"); raise SystemExit(1)

print("URL:", target)
print("TITLE:", d.title)

info = d.execute_script(r"""
(function(){
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const tas = Array.from(document.querySelectorAll('textarea')).map(el=>({
    id: el.id, cls: (el.className||'').slice(0,60), ph: el.placeholder||'',
    vis: visible(el), val: (el.value||'').slice(0,40)
  }));
  const ces = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]')).map(el=>({
    cls: (el.className||'').slice(0,60), vis: visible(el), txt: (el.innerText||'').slice(0,40)
  }));
  const btns = Array.from(document.querySelectorAll('button,[role="button"]'))
    .filter(visible).map(el=>({
      label: (el.getAttribute('aria-label')||''), testid: (el.getAttribute('data-testid')||''),
      cls: (el.className||'').slice(0,50), disabled: el.disabled
    })).slice(0,20);
  // look for sign-in / quota walls
  const bodyText = (document.body.innerText||'').slice(0,600);
  return {textareas: tas, contenteditables: ces, buttons: btns, bodyHead: bodyText};
})()
""")
print(json.dumps(info, indent=2)[:3000])
