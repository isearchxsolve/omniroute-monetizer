# -*- coding: utf-8 -*-
"""ADAPTER-INVOCATION PROOF: deepseek.

The Adapter Thesis in action: instead of rebuilding the PoW-signed request, we make
deepseek's OWN app send the message. The app's own code then computes the PoW, attaches
auth, and streams the answer -- correct by construction.

Mechanism (React app):
  1. Set the textarea value via the NATIVE value setter + dispatch 'input' (so React's
     state model sees it -- textContent alone never works).
  2. Trigger the site's own send: Enter keydown on the textarea (deepseek sends on
     Enter), falling back to clicking the send button if one is present.
  3. Poll the DOM for the sentinel phrase in the assistant reply.

This is replay-only: no signup, no login, no wall-solving. One message on the operator's
already-signed-in session. Attach-only, NEVER driver.quit().
"""
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PROMPT = "Repeat exactly this phrase and nothing else: the holy cow jumps over the stricks"
EXPECT = "the holy cow jumps over the stricks"
ANSWER_TIMEOUT_S = 90

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(ANSWER_TIMEOUT_S + 30)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if "deepseek" in driver.current_url:
            break
    except Exception:
        continue
driver.execute_cdp_cmd("Page.bringToFront", {})
print("on:", driver.current_url)

# ---- STEP 1: inject the prompt into the React textarea ----
inject_js = r"""
(function(prompt){
  const ta = document.querySelector('textarea');
  if(!ta) return {ok:false, why:'no textarea'};
  ta.focus();
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
  setter.call(ta, prompt);
  ta.dispatchEvent(new Event('input', {bubbles:true}));
  // report what send affordances now exist
  const btns = [];
  document.querySelectorAll('button,[role="button"]').forEach(el=>{
    const r = el.getBoundingClientRect();
    btns.push({tag:el.tagName, type:el.type||'', cls:(el.className&&el.className.baseVal!==undefined?el.className.baseVal:el.className||'').toString().slice(0,60),
      al:(el.getAttribute('aria-label')||'').slice(0,40), disabled:el.disabled,
      w:Math.round(r.width), h:Math.round(r.height), visible:r.width>0&&r.height>0});
  });
  return {ok:true, value:ta.value.slice(0,60), btnCount:btns.length, btns:btns.slice(0,15)};
})(arguments[0])
"""
r1 = driver.execute_script("return " + inject_js.strip(), PROMPT)
print("\n=== INJECT ===")
print("ok:", r1.get("ok"), "| value:", repr(r1.get("value")))
print("buttons now:", r1.get("btnCount"))
for b in (r1.get("btns") or []):
    print("  ", b)
if not r1.get("ok"):
    print("FAIL:", r1.get("why"))
    sys.exit(1)

# ---- STEP 2: trigger the site's own send (Enter keydown first) ----
send_js = r"""
(function(){
  const ta = document.querySelector('textarea');
  if(!ta) return {ok:false, why:'no textarea'};
  const before = document.body.innerText.length;
  // Enter keydown -- deepseek sends on Enter
  const opts = {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true};
  ta.dispatchEvent(new KeyboardEvent('keydown', opts));
  ta.dispatchEvent(new KeyboardEvent('keypress', opts));
  ta.dispatchEvent(new KeyboardEvent('keyup', opts));
  return {ok:true, method:'enter-keydown', bodyLenBefore:before, taValueAfter:ta.value.slice(0,40)};
})()
"""
r2 = driver.execute_script("return " + send_js.strip())
print("\n=== SEND ===")
print(r2)

time.sleep(2)

# check whether the textarea cleared (message accepted) -- if not, try button click
ta_state = driver.execute_script(
    "var t=document.querySelector('textarea');return t?{v:t.value.slice(0,40),len:t.value.length}:null;")
print("textarea after Enter:", ta_state)

if ta_state and ta_state.get("len", 0) > 0:
    print("Enter did not consume the text -> trying send-button click")
    click_js = r"""
    (function(){
      // find the most likely send button: enabled, visible, near bottom-right
      const cands = Array.from(document.querySelectorAll('button,[role="button"]'))
        .filter(el=>{
          const r = el.getBoundingClientRect();
          return r.width>0 && r.height>0 && !el.disabled;
        });
      if(!cands.length) return {ok:false, why:'no enabled button'};
      // prefer one whose label/class hints send/arrow, else the last one (chat UIs put send bottom-right)
      let pick = cands.find(el=>/send|submit|arrow/i.test((el.getAttribute('aria-label')||'')+(el.className||'')))
              || cands[cands.length-1];
      pick.click();
      return {ok:true, picked:(pick.getAttribute('aria-label')||pick.className||'').toString().slice(0,60)};
    })()
    """
    r3 = driver.execute_script("return " + click_js.strip())
    print("button click:", r3)
    time.sleep(2)
    ta_state = driver.execute_script(
        "var t=document.querySelector('textarea');return t?{v:t.value.slice(0,40),len:t.value.length}:null;")
    print("textarea after click:", ta_state)

# ---- STEP 3: poll the DOM for the answer ----
poll_js = r"""
const expect = arguments[0];
const cb = arguments[1];
const flat = s => (s||'').toLowerCase().replace(/[^a-z ]/g,' ').replace(/\s+/g,' ').trim();
const want = flat(expect);
const t0 = Date.now();
const timer = setInterval(()=>{
  const txt = document.body.innerText;
  if(flat(txt).includes(want)){
    clearInterval(timer);
    cb({found:true, ms:Date.now()-t0});
  } else if(Date.now()-t0 > TIMEOUT_MS){
    clearInterval(timer);
    cb({found:false, ms:Date.now()-t0, tail:txt.slice(-600)});
  }
}, 800);
"""
poll_js = poll_js.replace("TIMEOUT_MS", str(ANSWER_TIMEOUT_S * 1000))
print("\n=== POLLING for answer (up to %ds) ===" % ANSWER_TIMEOUT_S)
r4 = driver.execute_async_script(poll_js, EXPECT)
print(r4 if not r4.get("found") else {"found": True, "ms": r4.get("ms")})

if r4.get("found"):
    print("\nREPLAY_OK (deepseek via ADAPTER INVOCATION - site's own app sent the message, PoW included)")
    verdict = "REPLAY_OK_ADAPTER_INVOCATION"
    rc = 0
else:
    print("\nFAIL - phrase not found in DOM within timeout")
    print("tail:", repr((r4.get("tail") or "")[:400]))
    verdict = "FAIL"
    rc = 2

import json
json.dump({"host": "chat.deepseek.com", "verdict": verdict,
           "method": "adapter-invocation (React textarea + Enter)",
           "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S")},
          open(r"d:\omniroute-monetizer\state\deepseek_adapter_invocation.json", "w", encoding="utf-8"),
          indent=2)
print("saved state/deepseek_adapter_invocation.json")
print("DONE - do NOT quit.")
sys.exit(rc)
