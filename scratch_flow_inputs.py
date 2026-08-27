# -*- coding: utf-8 -*-
"""Classify Flow NO_COMPOSER: enumerate ALL input-like elements on the project page,
including contenteditable=plaintext-only, with sizes + visibility. Read-only."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROJ = "https://labs.google/fx/tools/flow/project/0db18532-cdf2-4d16-a2d4-c3d69e0202c2"

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(20)

# switch to the labs.google tab and navigate to the project page
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
    except Exception:
        continue
    if "labs.google" in (driver.current_url or ""):
        if "/project/" not in driver.current_url:
            driver.get(PROJ)
        break

time.sleep(8)  # let the WebGL app settle

JS = r"""
return (() => {
  const shadows = (root, acc=[]) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = w.nextNode())) if (n.shadowRoot) { acc.push(n.shadowRoot); shadows(n.shadowRoot, acc); }
    return acc;
  };
  const roots = [document, ...shadows(document)];
  const out = [];
  for (const r of roots) {
    for (const el of r.querySelectorAll('textarea, [contenteditable], input[type="text"], input[type="search"], [role="textbox"]')) {
      const rect = el.getBoundingClientRect();
      const st = el.ownerDocument.defaultView.getComputedStyle(el);
      out.push({
        tag: el.tagName.toLowerCase(),
        ce: el.getAttribute ? (el.getAttribute('contenteditable')||'') : '',
        role: el.getAttribute ? (el.getAttribute('role')||'') : '',
        ph: (el.placeholder||'').slice(0,30),
        cls: ((el.className && el.className.baseVal !== undefined) ? '' : (el.className||'')).toString().slice(0,40),
        w: Math.round(rect.width), h: Math.round(rect.height),
        top: Math.round(rect.top), left: Math.round(rect.left),
        disp: st.display, vis: st.visibility, op: st.opacity,
        dis: !!el.disabled, ro: !!el.readOnly
      });
    }
  }
  out.sort((a,b)=>a.top-b.top);
  return JSON.stringify({url: location.href, ready: document.readyState, vh: window.innerHeight, count: out.length, els: out.slice(0,25)});
})()
"""

info = json.loads(driver.execute_script(JS) or "{}")
print("url:", info.get("url"), " ready:", info.get("ready"), " input-like count:", info.get("count"))
for e in info.get("els", []):
    print("  ", e)
