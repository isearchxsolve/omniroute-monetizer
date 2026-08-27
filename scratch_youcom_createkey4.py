# -*- coding: utf-8 -*-
"""you.com: create ONE fresh key, capture the ydc-sk- one-time reveal (NOT the name field).
Non-destructive: deletes nothing. NEVER prints the key. Saves to gitignored state/secrets."""
import json, time, os, re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

SECRET_PATH = "state/secrets/youcom_api_key.json"
KEY_NAME = "omniroute-auto-%d" % int(time.time())

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

if "api-keys" not in d.current_url:
    d.get("https://you.com/platform/api-keys")
    time.sleep(4)
print("on:", d.current_url)

# Fill Key Name (input nearest the 'Create new key' heading)
filled = d.execute_script(r"""
const name=arguments[0];
return (function(){
  function visible(el){const r=el.getBoundingClientRect();if(r.width<=0||r.height<=0)return false;const st=getComputedStyle(el);return st.display!=='none'&&st.visibility!=='hidden';}
  const inputs=Array.from(document.querySelectorAll('input[type="text"],input:not([type]),input[type="search"]')).filter(visible);
  if(!inputs.length) return {ok:false,why:'no input'};
  const h2=Array.from(document.querySelectorAll('h1,h2,h3')).find(h=>/create new key/i.test(h.innerText||''));
  let el=inputs[0];
  if(h2){const hr=h2.getBoundingClientRect();let best=1e9;for(const i of inputs){const r=i.getBoundingClientRect();const dist=Math.hypot(r.x-hr.x,r.y-hr.y);if(dist<best){best=dist;el=i;}}}
  const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
  const tr=el._valueTracker; if(tr) tr.setValue('');
  setter.call(el,name);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return {ok:true,domValue:el.value};
})()
""", KEY_NAME)
print("fill name:", json.dumps(filled))
time.sleep(1)

# Click Create
clicked = d.execute_script(r"""
return (function(){
  function visible(el){const r=el.getBoundingClientRect();if(r.width<=0||r.height<=0)return false;const st=getComputedStyle(el);return st.display!=='none'&&st.visibility!=='hidden';}
  const btns=Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
  const t=btns.find(b=>/^create$/i.test((b.innerText||'').trim()));
  if(t){t.click();return t.innerText.trim();}
  return {fail:true,btns:btns.map(b=>(b.innerText||'').trim()).filter(Boolean).slice(0,15)};
})()
""")
print("clicked create:", clicked)

# Poll for the ydc-sk- reveal (the REAL key), checking body + all value nodes
captured=None
for attempt in range(25):
    sources = [d.execute_script("return document.body.innerText||''")]
    vals = d.execute_script(r"""
    return Array.from(document.querySelectorAll('input,textarea,pre,code')).map(n=>(n.value!==undefined&&n.value)?n.value:(n.innerText||'')).filter(Boolean);
    """)
    sources.extend(vals)
    for v in sources:
        m = re.search(r'ydc-sk-[A-Za-z0-9_\-\.=+/]{16,}', v)
        if m:
            captured = m.group(0)
            break
    if captured:
        break
    time.sleep(1.2)

if captured:
    os.makedirs(os.path.dirname(SECRET_PATH), exist_ok=True)
    rec={
        "host":"api.you.com",
        "modality":"chat",
        "site":"You.com Answer API",
        "api_key":captured,
        "key_name":KEY_NAME,
        "credits_note":"free promotional credits, zero money invested (operator-confirmed)",
        "captured_at":int(time.time()),
    }
    with open(SECRET_PATH,"w",encoding="utf-8") as f:
        json.dump(rec,f,indent=1)
    print("\nREAL KEY CAPTURED -> saved to", SECRET_PATH)
    print("redacted:", captured[:10]+"..."+captured[-4:], "len", len(captured))
else:
    print("\nNO ydc-sk- KEY FOUND. Body head:")
    print((d.execute_script("return document.body.innerText||''")[:800]).replace("\n"," | "))
