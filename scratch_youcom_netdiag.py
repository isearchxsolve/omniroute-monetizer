# -*- coding: utf-8 -*-
"""you.com network diag: did the api.you.com fetch fire? Is an API key configured?
Check performance resource entries + storage for keys + any visible error toast."""
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

# 1) recent network resource entries mentioning you.com api / answer / cr-proxy
res = d.execute_script(r"""
return (function(){
  const entries = performance.getEntriesByType('resource')
    .map(e=>({name:e.name.slice(0,140), type:e.initiatorType, dur:Math.round(e.duration), status:e.responseStatus||null}))
    .filter(e=>/api\.you\.com|\/answer|cr-proxy|graphql|batch|v1\//i.test(e.name));
  return entries.slice(-25);
})()
""")
print("=== recent matching network entries ===")
for e in res:
    print(f"  [{e.get('status')}] {e.get('type','?'):10s} {e.get('dur',0):5d}ms {e.get('name')}")
if not res:
    print("  (none matched — the answer fetch likely NEVER fired)")

# 2) storage scan for API key presence (never print the key itself)
stor = d.execute_script(r"""
return (function(){
  const out = {localStorage:{}, sessionStorage:{}};
  try {
    for(let i=0;i<localStorage.length;i++){
      const k = localStorage.key(i);
      if(/api|key|token|auth|ydc|you/i.test(k)){
        const v = localStorage.getItem(k)||'';
        out.localStorage[k] = {len:v.length, head:v.slice(0,8)+'...'};
      }
    }
    for(let i=0;i<sessionStorage.length;i++){
      const k = sessionStorage.key(i);
      if(/api|key|token|auth|ydc|you/i.test(k)){
        const v = sessionStorage.getItem(k)||'';
        out.sessionStorage[k] = {len:v.length, head:v.slice(0,8)+'...'};
      }
    }
  } catch(e){ out.err = String(e); }
  return out;
})()
""")
print("\n=== storage keys matching api/key/token/auth ===")
print(json.dumps(stor, indent=2)[:1200])

# 3) cookies present for you.com (names only)
ck = d.execute_script("return document.cookie.split(';').map(c=>c.trim().split('=')[0]).filter(Boolean)")
print("\n=== cookie names ===")
print(ck)

# 4) any visible toast/alert/error text
toast = d.execute_script(r"""
return (function(){
  const body = document.body.innerText||'';
  const lines = body.split('\n').map(l=>l.trim()).filter(Boolean);
  const hits = lines.filter(l=>/error|fail|invalid|missing|provide|enter.*key|api key|unauthorized|sign in|log in/i.test(l));
  return hits.slice(0,15);
})()
""")
print("\n=== error-ish visible lines ===")
for t in toast:
    print("  ", t[:120])
