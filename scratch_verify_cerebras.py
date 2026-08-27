# -*- coding: utf-8 -*-
"""Verify cerebras: is the phrase in a FRESH assistant reply, or leftover from the
earlier failed run / the echoed prompt? Read-only DOM inspection."""
import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PHRASE = "the holy cow jumps over the stricks"

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
(function(phrase){
  const out = {containers: [], textarea: null, body_has_phrase: false};
  const sels = '[class*="message"],[class*="Message"],[class*="markdown"],[class*="turn"],[class*="chat-item"],[class*="answer"],[class*="response"],[data-role]';
  const seen = new Set();
  document.querySelectorAll(sels).forEach(el=>{
    if(seen.has(el)) return; seen.add(el);
    const t = (el.innerText||'').trim();
    if(!t) return;
    out.containers.push({
      cls: (el.className||'').toString().replace(/\s+/g,' ').slice(0,90),
      role: el.getAttribute('data-role')||'',
      len: t.length,
      head: t.slice(0,70),
      has_phrase: t.toLowerCase().includes(phrase.toLowerCase())
    });
  });
  // visible textarea / contenteditable state
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const ta = Array.from(document.querySelectorAll('textarea')).find(e=>visible(e) && !/recaptcha/i.test((e.id||'')+(e.className||'')));
  const ce = Array.from(document.querySelectorAll('[contenteditable="true"],[contenteditable="plaintext-only"]')).find(e=>visible(e));
  const inp = ta || ce;
  if(inp){
    out.textarea = {
      tag: inp.tagName,
      id: inp.id, cls: (inp.className||'').toString().slice(0,60),
      len: ((inp.value!==undefined?inp.value:inp.innerText)||'').length,
      head: ((inp.value!==undefined?inp.value:inp.innerText)||'').slice(0,60)
    };
  }
  out.body_has_phrase = (document.body.innerText||'').toLowerCase().includes(phrase.toLowerCase());
  return out;
})(arguments[0])
"""
r = d.execute_script("return " + JS.strip(), PHRASE)
print("body has phrase:", r["body_has_phrase"])
print("input state:", json.dumps(r["textarea"], ensure_ascii=False))
print("\n=== CONTAINERS (count=%d) ===" % len(r["containers"]))
for i, c in enumerate(r["containers"]):
    mark = " <== PHRASE" if c["has_phrase"] else ""
    print("[%2d] len=%-5d role=%-10s cls=%-60s %r%s" % (
        i, c["len"], c["role"], c["cls"][:60], c["head"], mark))
print("DONE - do NOT quit.")
