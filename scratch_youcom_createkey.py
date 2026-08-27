# -*- coding: utf-8 -*-
"""you.com: create a NEW API key via the dashboard (free credits, zero money invested),
capture the one-time plaintext reveal, save to gitignored state/secrets. NEVER print the key.
Follows AGENTS.md Resolution 1 (Create New Key lifecycle)."""
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

d.get("https://you.com/platform/api-keys")
time.sleep(4)
print("on:", d.current_url)

# Step 1: click "Create new key"
clicked = d.execute_script(r"""
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  const btns=Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(visible);
  const t=btns.find(b=>/create new key|create key|new key|generate/i.test((b.innerText||'').trim()));
  if(t){ t.click(); return (t.innerText||'').trim(); }
  return null;
})()
""")
print("clicked create:", clicked)
time.sleep(2)

# Step 2: fill the key name field in the dialog
filled = d.execute_script(r"""
const name = arguments[0];
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  // find a visible text input inside a dialog/modal
  const dlg=document.querySelector('[role="dialog"],[data-state="open"],dialog,.modal,[class*="dialog" i],[class*="modal" i]')||document;
  const inputs=Array.from(dlg.querySelectorAll('input[type="text"],input:not([type]),input[type="search"]')).filter(visible);
  if(!inputs.length) return {ok:false, why:'no input in dialog', inputs:inputs.length};
  const el=inputs[0];
  const setter=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
  const tracker=el._valueTracker; if(tracker) tracker.setValue('');
  setter.call(el, name);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return {ok:true, domValue:el.value, ph:el.placeholder||''};
})()
""", KEY_NAME)
print("fill name:", json.dumps(filled))
time.sleep(1)

# Step 3: click the confirm/Create button inside the dialog
confirmed = d.execute_script(r"""
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  const dlg=document.querySelector('[role="dialog"],[data-state="open"],dialog,.modal,[class*="dialog" i],[class*="modal" i]')||document;
  const btns=Array.from(dlg.querySelectorAll('button,[role="button"]')).filter(visible);
  // prefer submit / create / confirm, avoid cancel
  const cand=btns.filter(b=>!/cancel|close|back/i.test((b.innerText||'').trim()));
  const t=cand.find(b=>/create|confirm|submit|generate|save|add/i.test((b.innerText||'').trim())) || (cand[cand.length-1]);
  if(t){ t.click(); return (t.innerText||'').trim(); }
  return null;
})()
""")
print("confirmed:", confirmed)
time.sleep(3)

# Step 4: capture the one-time plaintext key from the reveal modal
def looks_like_key(s):
    s=(s or '').strip()
    return len(s)>=20 and re.fullmatch(r'[A-Za-z0-9_\-\.=+/]+', s) is not None

captured=None
for attempt in range(12):
    cand = d.execute_script(r"""
    return (function(){
      const out=[];
      // code blocks, pre, readonly inputs, and any element whose text looks like a key
      const nodes=Array.from(document.querySelectorAll('pre,code,input[readonly],input[type="text"],textarea,[class*="key" i],[class*="token" i],[class*="secret" i]'));
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
    # last resort: scan whole body for a long token
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
    print("\nNO KEY CAPTURED — dumping dialog text for diagnosis")
    dlg=d.execute_script(r"""
    const dlg=document.querySelector('[role="dialog"],[data-state="open"],dialog,.modal')||document.body;
    return (dlg.innerText||'').slice(0,600);
    """)
    print(dlg.replace("\n"," | "))
