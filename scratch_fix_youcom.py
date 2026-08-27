# -*- coding: utf-8 -*-
"""you.com fix test: React valueTracker injection + explicit Run-query click + response discovery."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(60)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            break
    except Exception:
        continue
else:
    raise SystemExit("NO you.com tab")

PROMPT = "Reply with exactly one word: pong."

# 1) inject with React _valueTracker reset
r1 = d.execute_script(r"""
return (function(prompt){
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const ta = Array.from(document.querySelectorAll('textarea')).find(e=>visible(e));
  if(!ta) return {ok:false, why:'no textarea'};
  ta.focus();
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
  setter.call(ta, prompt);
  // React controlled-input trick: reset the value tracker so React's onChange fires
  const tracker = ta._valueTracker;
  if(tracker){ tracker.setValue(''); }
  ta.dispatchEvent(new Event('input', {bubbles:true}));
  ta.dispatchEvent(new Event('change', {bubbles:true}));
  return {ok:true, domValue:(ta.value||'').slice(0,60), hasTracker: !!tracker};
})(arguments[0])
""", PROMPT)
print("INJECT:", json.dumps(r1))
time.sleep(1)

# 2) click Run query (type=submit)
r2 = d.execute_script(r"""
return (function(){
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const btn = Array.from(document.querySelectorAll('button')).find(el=>visible(el) && el.getAttribute('type')==='submit' && !el.disabled);
  if(!btn) return {ok:false, why:'no submit button'};
  btn.click();
  return {ok:true, txt:(btn.innerText||'').trim()};
})()
""")
print("CLICK:", json.dumps(r2))

# 3) wait and watch what changes — snapshot body text growth + new pre/code/json blocks
time.sleep(8)
r3 = d.execute_script(r"""
return (function(){
  const pres = Array.from(document.querySelectorAll('pre,code,[class*="response"],[class*="Response"],[class*="result"],[class*="Result"],[class*="output"],[class*="Output"],[class*="json"]'))
    .map(el=>({cls:((el.className&&el.className.baseVal!==undefined)?el.className.baseVal:(el.className||'')+'').slice(0,60),
               txt:(el.innerText||'').slice(0,200)}))
    .filter(x=>x.txt.trim());
  return {url: location.href.slice(0,120), bodyLen:(document.body.innerText||'').length,
          pres: pres.slice(0,8), bodyTail:(document.body.innerText||'').slice(-500)};
})()
""")
print("AFTER:", json.dumps(r3, indent=2)[:2500])
