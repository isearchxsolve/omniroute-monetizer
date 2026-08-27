# -*- coding: utf-8 -*-
"""VERIFY the deepseek answer is in the ASSISTANT reply, not the echoed user prompt.

The sentinel phrase is a substring of the injected prompt, so a whole-body innerText
match is ambiguous. We must isolate the assistant's message container and confirm the
phrase is there, and ideally that the assistant reply is SHORT (just the phrase), which
a real 'repeat exactly' answer would be.

Read-only. Attach-only, NEVER driver.quit().
"""
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

EXPECT = "the holy cow jumps over the stricks"

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(60)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if "deepseek" in driver.current_url:
            break
    except Exception:
        continue
driver.execute_cdp_cmd("Page.bringToFront", {})
print("on:", driver.current_url)

probe = r"""
(function(){
  const flat = s => (s||'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
  const want = flat(EXPECT_PH);
  const out = {containers:[], hits:[]};

  // Find all message-like containers. DeepSeek chat renders each turn in its own block.
  // Try several common selectors.
  const sels = [
    '[class*="message"]', '[class*="Message"]',
    '[class*="chat-item"]', '[class*="turn"]',
    '[data-role]', '[class*="assistant"]', '[class*="user"]',
    '[class*="markdown"]', '[class*="answer"]', '[class*="response"]'
  ];
  const seen = new Set();
  const nodes = [];
  for(const s of sels){
    document.querySelectorAll(s).forEach(el=>{
      if(seen.has(el)) return;
      seen.add(el);
      nodes.push(el);
    });
  }
  // Keep only nodes whose own text contains the phrase (direct hits)
  for(const el of nodes){
    const t = el.innerText || '';
    if(flat(t).includes(want)){
      const r = el.getBoundingClientRect();
      out.hits.push({
        cls:(el.className&&el.className.baseVal!==undefined?el.className.baseVal:(el.className||'')).toString().slice(0,70),
        role: el.getAttribute('data-role')||'',
        len: t.length,
        w:Math.round(r.width), h:Math.round(r.height),
        text: t.slice(0,220)
      });
    }
  }
  // Also: find the LAST few text blocks on the page (the newest turn is at the bottom)
  const all = Array.from(document.querySelectorAll('div,p,section,article'))
    .filter(el=>{
      const t=(el.innerText||'').trim();
      return t.length>0 && t.length<400 && flat(t).includes(want) && el.children.length<=2;
    });
  out.leafHits = all.slice(-6).map(el=>({
    cls:((el.className&&el.className.baseVal!==undefined)?el.className.baseVal:(el.className||'')).toString().slice(0,60),
    len:(el.innerText||'').length,
    text:(el.innerText||'').slice(0,200)
  }));
  return out;
})()
"""
probe = probe.replace("EXPECT_PH", '"' + EXPECT + '"')
res = driver.execute_script("return " + probe.strip())

print("\n=== CONTAINER HITS (elements whose text contains the phrase) ===")
for x in res.get("hits", [])[:20]:
    print("  cls=%r role=%r len=%d %dx%d" % (x["cls"], x["role"], x["len"], x["w"], x["h"]))
    print("     text:", repr(x["text"]))

print("\n=== LEAF HITS (smallest blocks containing the phrase, last 6) ===")
for x in res.get("leafHits", []):
    print("  cls=%r len=%d" % (x["cls"], x["len"]))
    print("     text:", repr(x["text"]))

# Verdict: a REAL 'repeat exactly' assistant answer is SHORT (<= ~80 chars) and equals the phrase.
# The user prompt is LONG (contains 'Repeat exactly this phrase and nothing else:').
short_hits = [x for x in res.get("leafHits", []) if x["len"] <= 90]
print("\n=== ANALYSIS ===")
print("leaf hits total:", len(res.get("leafHits", [])), "| short (<=90 chars):", len(short_hits))
if short_hits:
    print("A SHORT block containing exactly the phrase exists -> likely the ASSISTANT reply.")
    for x in short_hits:
        print("   SHORT HIT:", repr(x["text"]))
else:
    print("Only LONG blocks contain the phrase -> likely just the echoed USER prompt. NOT a real answer.")
print("DONE (read-only) - do NOT quit.")
