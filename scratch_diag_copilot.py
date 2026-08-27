# -*- coding: utf-8 -*-
"""Diagnose copilot.microsoft.com response container after a sent message.
The generic POLL_JS grabbed 'Edit in a page' (UI chrome). Find the real reply node."""
import json
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(20)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if "copilot.microsoft.com" in (driver.current_url or ""):
            break
    except Exception:
        continue

JS = r"""
try {
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  // find elements containing the word 'Omni' (our sentinel reply)
  const all = Array.from(document.querySelectorAll('div,section,article,p,span'));
  const hits = all.filter(el => visible(el) && /\bOmni\b/.test(el.innerText||'')
      && (el.innerText||'').length < 400);
  // keep the deepest (most specific) hits
  const out = hits.slice(-8).map(el => ({
    tag: el.tagName,
    cls: ((el.className||'')+'').replace(/\s+/g,' ').slice(0,100),
    id: el.id || '',
    attrs: Array.from(el.attributes).filter(a=>a.name.startsWith('data-')).map(a=>a.name+'='+a.value.slice(0,20)).slice(0,4),
    text: (el.innerText||'').replace(/\s+/g,' ').slice(0,80)
  }));
  return JSON.stringify(out, null, 1);
} catch(e){ return 'ERR '+String(e); }
"""
print(driver.execute_script(JS))
