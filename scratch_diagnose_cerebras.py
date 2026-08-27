# -*- coding: utf-8 -*-
"""Diagnose cerebras chat tab: textarea state, form, candidate send buttons, and
whether our injected prompt is still sitting unsent. Read-only."""
import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(30)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "cerebras" in d.current_url:
            break
    except Exception:
        continue
print("on:", d.current_url)

JS = r"""
(function(){
  const out = {};
  const ta = document.querySelector('textarea');
  out.textarea = ta ? {
    value_len: (ta.value||'').length,
    value_head: (ta.value||'').slice(0,60),
    placeholder: ta.placeholder,
    disabled: ta.disabled,
    in_form: !!ta.closest('form'),
    id: ta.id, cls: (ta.className||'').slice(0,80)
  } : null;
  // all buttons with geometry + labels
  out.buttons = Array.from(document.querySelectorAll('button,[role="button"]')).map(el=>{
    const r = el.getBoundingClientRect();
    return {
      tag: el.tagName,
      aria: el.getAttribute('aria-label')||'',
      title: el.getAttribute('title')||'',
      type: el.getAttribute('type')||'',
      cls: (el.className||'').toString().slice(0,70),
      text: (el.innerText||'').trim().slice(0,30),
      disabled: el.disabled,
      visible: r.width>0 && r.height>0,
      x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)
    };
  }).filter(b=>b.visible);
  // any element whose aria/class screams send
  out.sendish = Array.from(document.querySelectorAll('[aria-label*="send" i],[aria-label*="Send"],[data-testid*="send" i],button[type="submit"]')).map(el=>({
    tag: el.tagName, aria: el.getAttribute('aria-label')||'', type: el.getAttribute('type')||'',
    cls: (el.className||'').toString().slice(0,70),
    disabled: el.disabled
  }));
  // does the page already show our prompt as a user message?
  const body = document.body.innerText||'';
  out.prompt_in_dom = body.includes('holy cow');
  // framework hints
  const root = document.getElementById('root') || document.getElementById('__next') || document.body.firstElementChild;
  out.framework_keys = root ? Object.keys(root).filter(k=>k.startsWith('__react')||k.startsWith('__next')).slice(0,5) : [];
  return out;
})()
"""
r = d.execute_script("return " + JS.strip())
print(json.dumps(r, indent=2, ensure_ascii=False))
print("DONE - do NOT quit.")
