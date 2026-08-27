# -*- coding: utf-8 -*-
"""you.com DECISIVE test: inject distinctive query, click Run, wait for response JSON to CHANGE
from the current (stale aurora) one. Proves whether injection+submit really executes."""
import json, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(90)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            break
    except Exception:
        continue
else:
    raise SystemExit("NO you.com tab")

def get_response_json():
    """Return the text of the response .language-json block (the ANSWER json, not the curl)."""
    return d.execute_script(r"""
    return (function(){
      const blocks = Array.from(document.querySelectorAll('.language-json'))
        .map(el=>(el.innerText||'').trim()).filter(Boolean);
      // the response json contains "answer"; the curl example is language-bash
      for(const b of blocks){ if(b.includes('"answer"')) return b; }
      return null;
    })()
    """)

stale = get_response_json()
print("STALE response present:", bool(stale), "| head:", (stale or "")[:60].replace("\n"," "))

QUERY = "What is the capital of France? Reply with just the city name."

# inject with React valueTracker reset
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
  const tracker = ta._valueTracker;
  if(tracker){ tracker.setValue(''); }
  ta.dispatchEvent(new Event('input', {bubbles:true}));
  ta.dispatchEvent(new Event('change', {bubbles:true}));
  return {ok:true, domValue:(ta.value||'').slice(0,60)};
})(arguments[0])
""", QUERY)
print("INJECT:", json.dumps(r1))
time.sleep(1)

# click Run query (type=submit)
r2 = d.execute_script(r"""
return (function(){
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const btn = Array.from(document.querySelectorAll('button')).find(el=>visible(el) && el.getAttribute('type')==='submit' && !el.disabled);
  if(!btn) return {ok:false, why:'no submit'};
  btn.click();
  return {ok:true, txt:(btn.innerText||'').trim()};
})()
""")
print("CLICK:", json.dumps(r2))
print("URL after click:", d.current_url[:110])

# poll until response JSON changes from stale (or a fresh answer appears)
t0 = time.time()
new_resp = None
for i in range(45):
    time.sleep(2)
    cur = get_response_json()
    if cur and cur != stale:
        new_resp = cur
        break
    # also accept: stale was None and now we have any answer
    if stale is None and cur:
        new_resp = cur
        break

el = time.time() - t0
if new_resp:
    try:
        parsed = json.loads(new_resp)
        ans = parsed.get("answer", "")
        print(f"\nCHANGED after {el:.1f}s")
        print("ANSWER:", ans[:300])
    except Exception as e:
        print(f"\nCHANGED after {el:.1f}s but not valid JSON: {e}")
        print("RAW:", new_resp[:300])
else:
    print(f"\nNO CHANGE after {el:.1f}s — response panel still shows stale/none")
    print("current url:", d.current_url[:110])
