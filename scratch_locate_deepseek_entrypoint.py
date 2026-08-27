# -*- coding: utf-8 -*-
"""ADAPTER-INVOCATION STEP 1 (read-only): locate deepseek's send entry-point.

The Adapter Thesis says: don't rebuild the request, invoke the site's own sender.
Before we can invoke it we must LOCATE it. This script attaches to seat1, opens the
deepseek tab, and finds:
  1. The chat input element (textarea / contenteditable) and the send button.
  2. The event handler / function the UI calls on submit (by inspecting the DOM and
     the loaded JS for the send path).
  3. Any globally-reachable app state (React/Vue fiber, window.__*) that exposes a
     programmatic send.

Read-only: no message is sent, no request fired. Attach-only, NEVER driver.quit().
"""
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(120)

# focus the deepseek tab
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if "deepseek" in driver.current_url:
            break
    except Exception:
        continue
driver.execute_cdp_cmd("Page.bringToFront", {})
print("on:", driver.current_url)

# ---- 1. the input + send button ----
probe_dom = r"""
(function(){
  const out = {inputs:[], buttons:[], editables:[]};
  // textareas
  document.querySelectorAll('textarea').forEach(el=>{
    out.inputs.push({tag:'textarea', id:el.id, cls:(el.className||'').slice(0,80),
      ph:el.placeholder||'', visible:!!(el.offsetParent)});
  });
  // contenteditable
  document.querySelectorAll('[contenteditable="true"]').forEach(el=>{
    out.editables.push({tag:el.tagName, id:el.id, cls:(el.className||'').slice(0,80),
      visible:!!(el.offsetParent)});
  });
  // candidate send buttons: aria-label / text / data-testid
  document.querySelectorAll('button,[role="button"]').forEach(el=>{
    const t=(el.textContent||'').trim().toLowerCase();
    const al=(el.getAttribute('aria-label')||'').toLowerCase();
    const dt=el.getAttribute('data-testid')||'';
    if(/send|submit|arrow|enter/.test(t+' '+al+' '+dt) || el.type==='submit'){
      out.buttons.push({tag:el.tagName, type:el.type, al:al.slice(0,40),
        dt:dt.slice(0,40), text:t.slice(0,30), cls:(el.className||'').slice(0,60),
        disabled:el.disabled, visible:!!(el.offsetParent)});
    }
  });
  return out;
})()
"""
dom = driver.execute_script("return " + probe_dom.strip())
print("\n=== INPUTS ===")
for x in dom.get("inputs", []):
    print(" ", x)
print("=== CONTENTEDITABLES ===")
for x in dom.get("editables", []):
    print(" ", x)
print("=== SEND BUTTON CANDIDATES ===")
for x in dom.get("buttons", []):
    print(" ", x)

# ---- 2. global app handles (React fiber / framework state) ----
probe_globals = r"""
(function(){
  const out = {framework:null, globals:[], reactRoot:false};
  // detect framework
  const root = document.getElementById('root') || document.getElementById('app')
             || document.querySelector('#__next') || document.body.firstElementChild;
  if (root) {
    const keys = Object.keys(root);
    if (keys.some(k=>k.startsWith('__reactFiber')||k.startsWith('__reactInternalInstance'))) out.framework='react';
    else if (keys.some(k=>k.startsWith('__vue'))) out.framework='vue';
    out.rootKeys = keys.filter(k=>k.startsWith('__')).slice(0,6);
  }
  // interesting window globals
  for (const k of Object.keys(window)) {
    if (/deepseek|chat|store|app|sdk|api|state/i.test(k) && !/^(webkit|chrome|on)/i.test(k)) {
      out.globals.push(k);
    }
  }
  out.globals = out.globals.slice(0,40);
  return out;
})()
"""
gl = driver.execute_script("return " + probe_globals.strip())
print("\n=== FRAMEWORK / GLOBALS ===")
print("  framework:", gl.get("framework"))
print("  rootKeys:", gl.get("rootKeys"))
print("  globals:", gl.get("globals"))

# ---- 3. hunt the send path in loaded JS ----
inline = driver.execute_script(
    "return Array.from(document.scripts).filter(s=>!s.src).map(s=>s.textContent).join('\\n');")
srcs = driver.execute_script(
    "return Array.from(document.scripts).map(s=>s.src).filter(Boolean);")
blobs = [("inline", inline)]
for src in srcs:
    try:
        txt = driver.execute_script(
            "return fetch(arguments[0]).then(r=>r.text()).catch(e=>'');", src)
    except Exception:
        txt = ""
    if txt:
        blobs.append((src.split("/")[-1][:40], txt))

print("\n=== SEND-PATH EVIDENCE (chat/completions, sendMessage, submit handlers) ===")
seen = set()
count = 0
KEYWORDS = ["chat/completion", "sendMessage", "send_message", "submit", "onSend",
            "handleSend", "createChat", "completion", "generate", "pow", "challenge"]
for name, txt in blobs:
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), txt, re.IGNORECASE):
            start = max(0, m.start() - 80)
            end = min(len(txt), m.end() + 160)
            seg = txt[start:end].replace("\n", " ")
            key = seg[:50]
            if key in seen:
                continue
            seen.add(key)
            if any(c in seg for c in ("fetch", "ajax", "XMLHttp", "pow", "challenge",
                                      "completion", "send", "submit")):
                print("\n[%s] kw=%r" % (name, kw))
                print("  ..." + seg + "...")
                count += 1
                if count >= 20:
                    break
        if count >= 20:
            break
    if count >= 20:
        break

print("\n=== TOTAL send-path fragments: %d ===" % count)
print("DONE (read-only) - do NOT quit.")
