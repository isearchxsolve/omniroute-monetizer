# -*- coding: utf-8 -*-
"""you.com: inspect the post-create reveal to find the REAL key (not the name field)."""
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

print("on:", d.current_url)

# Dump every input/readonly/pre/code value with context, redacted
r = d.execute_script(r"""
return (function(){
  const out=[];
  const nodes=Array.from(document.querySelectorAll('input,textarea,pre,code'));
  nodes.forEach(n=>{
    const v=(n.value!==undefined && n.value!==null && n.value!=='')? n.value : (n.innerText||n.textContent||'');
    if(!v || !v.trim()) return;
    const rect=n.getBoundingClientRect();
    out.push({
      tag:n.tagName,
      type:n.getAttribute('type')||'',
      readonly:n.readOnly||null,
      id:(n.id||'').slice(0,40),
      ph:n.placeholder||'',
      vis: rect.width>0&&rect.height>0,
      len:v.trim().length,
      head:v.trim().slice(0,10),
      tail:v.trim().slice(-6)
    });
  });
  return out;
})()
""")
print("=== all value-bearing nodes (redacted) ===")
print(json.dumps(r, indent=1)[:2500])

# Also: is there a key listed in the keys table now?
table = d.execute_script(r"""
return (function(){
  const txt=document.body.innerText||'';
  const hasOmniroute=txt.includes('omniroute-auto');
  const rows=Array.from(document.querySelectorAll('table tr,[role="row"]')).map(r=>(r.innerText||'').replace(/\n/g,' | ').slice(0,80)).filter(Boolean);
  return {hasOmniroute, rows:rows.slice(0,8)};
})()
""")
print("\n=== keys table ===")
print(json.dumps(table, indent=1)[:800])
