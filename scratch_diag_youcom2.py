# -*- coding: utf-8 -*-
"""Diagnose you.com tab v2: enumerate ALL you.com tabs, wait for load, screenshot + DOM dump."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(30)

hits = []
for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            hits.append((h, d.current_url, d.title))
    except Exception:
        continue

print(f"{len(hits)} you.com tab(s):")
for h, u, t in hits:
    print(f"  [{h[:8]}] {u[:100]}\n      title={t[:60]}")

if not hits:
    raise SystemExit("NO you.com tab")

# use the last one (most recently found)
d.switch_to.window(hits[-1][0])
for _ in range(20):
    if d.execute_script("return document.readyState") == "complete":
        break
    time.sleep(0.5)
print("\nreadyState:", d.execute_script("return document.readyState"))
print("URL now:", d.current_url[:120])

d.save_screenshot("d:/omniroute-monetizer/state/diag_youcom.png")
print("screenshot -> state/diag_youcom.png")

info = d.execute_script(r"""
(function(){
  try {
    function visible(el){
      const r = el.getBoundingClientRect();
      if(r.width<=0 || r.height<=0) return false;
      const st = window.getComputedStyle(el);
      return st.display!=='none' && st.visibility!=='hidden';
    }
    const tas = Array.from(document.querySelectorAll('textarea')).map(el=>({
      id: el.id||'', cls: ((el.className||'')+'').slice(0,60), ph: el.placeholder||'',
      vis: visible(el), val: (el.value||'').slice(0,50)
    }));
    const ces = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]')).map(el=>({
      cls: ((el.className||'')+'').slice(0,60), vis: visible(el), txt: (el.innerText||'').slice(0,50)
    }));
    const btns = Array.from(document.querySelectorAll('button,[role="button"],svg[class*="send"],div[class*="send"]'))
      .filter(visible).map(el=>({
        tag: el.tagName, label: el.getAttribute('aria-label')||'',
        testid: el.getAttribute('data-testid')||'', cls: ((el.className&&el.className.baseVal!==undefined)?el.className.baseVal:(el.className||'')+'').slice(0,60),
        disabled: !!el.disabled, type: el.getAttribute('type')||''
      })).slice(0,25);
    const iframes = Array.from(document.querySelectorAll('iframe')).map(f=>({src:(f.src||'').slice(0,80), vis:visible(f)}));
    return {textareas: tas, contenteditables: ces, buttons: btns, iframes: iframes,
            bodyHead: (document.body? (document.body.innerText||'').slice(0,500) : 'NO BODY')};
  } catch(e) { return {error: String(e)}; }
})()
""")
print(json.dumps(info, indent=2)[:3500])
