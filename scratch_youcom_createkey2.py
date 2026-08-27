# -*- coding: utf-8 -*-
"""you.com: inline key-creation form (Key Name input + Create button), capture one-time reveal.
NEVER prints the key. Saves to gitignored state/secrets/youcom_api_key.json."""
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

# Step 1: find the Key Name input (near the 'Create new key' H2) and fill it
filled = d.execute_script(r"""
const name = arguments[0];
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  // all visible text inputs on the page
  const inputs=Array.from(document.querySelectorAll('input[type="text"],input:not([type]),input[type="search"]')).filter(visible);
  if(!inputs.length) return {ok:false, why:'no visible text input'};
  // pick the one closest to the 'Create new key' heading
  const h2=Array.from(document.querySelectorAll('h1,h2,h3')).find(h=>/create new key/i.test(h.innerText||''));
  let el=inputs[0];
  if(h2){
    const hr=h2.getBoundingClientRect();
    let best=1e9;
    for(const i of inputs){
      const r=i.getBoundingClientRect();
      const dist=Math.hypot(r.x-hr.x, r.y-hr.y);
      if(dist<best){best=dist; el=i;}
    }
  }
  const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
  const tracker=el._valueTracker; if(tracker) tracker.setValue('');
  setter.call(el, name);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return {ok:true, domValue:el.value, ph:el.placeholder||'', id:(el.id||'').slice(0,40)};
})()
""", KEY_NAME)
print("fill name:", json.dumps(filled))
time.sleep(1)

# Step 2: click the Create button (near the input, not cancel)
clicked = d.execute_script(r"""
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  const btns=Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
  const cand=btns.filter(b=>{
    const t=(b.innerText||'').trim();
    return t && /^create$/i.test(t) || /^create\b/i.test(t) && !/new key/i.test(t);
  });
  const t=cand[0] || btns.find(b=>/^create$/i.test((b.innerText||'').trim()));
  if(t){ t.click(); return (t.innerText||'').trim(); }
  return {fail:true, btns:btns.map(b=>(b.innerText||'').trim()).filter(Boolean).slice(0,15)};
})()
""")
print("clicked create:", json.dumps(clicked) if isinstance(clicked,dict) else clicked)
time.sleep(3)

# Step 3: capture the one-time plaintext key from the reveal
def looks_like_key(s):
    s=(s or '').strip()
    return len(s)>=20 and re.fullmatch(r'[A-Za-z0-9_\-\.=+/]+', s) is not None

captured=None
for attempt in range(14):
    cand = d.execute_script(r"""
    return (function(){
      const out=[];
      const nodes=Array.from(document.querySelectorAll('pre,code,input[readonly],input[type="text"],textarea,[class*="key" i],[class*="token" i],[class*="secret" i],[class*="reveal" i],[class*="copy" i]'));
      nodes.forEach(n=>{
        const v=(n.value!==undefined && n.value)? n.value : (n.innerText||n.textContent||'');
        if(v) out.push(v.trim());
      });
      return out;
    })()
    """)
    for v in cand:
        if looks_like_key(v):
            captured=v
            break
    if captured:
        break
    time.sleep(1.5)

if not captured:
    body=d.execute_script("return document.body.innerText||''")
    for tok in re.findall(r'[A-Za-z0-9_\-\.=+/]{24,}', body):
        if looks_like_key(tok):
            captured=tok
            break

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
    print("\nKEY CAPTURED -> saved to", SECRET_PATH)
    print("redacted:", captured[:6]+"..."+captured[-4:], "len", len(captured))
else:
    print("\nNO KEY CAPTURED — page text for diagnosis:")
    print((d.execute_script("return document.body.innerText||''")[:700]).replace("\n"," | "))
