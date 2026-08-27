# -*- coding: utf-8 -*-
"""you.com: open /platform/api-keys and report key surface (never print the key)."""
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

d.get("https://you.com/platform/api-keys")
time.sleep(4)
print("final url:", d.current_url)

body = d.execute_script("return (document.body.innerText||'').slice(0,900)")
print("=== body head ===")
print(body.replace("\n", " | ")[:700])

# buttons / actions available
btns = d.execute_script(r"""
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  const out=[];
  document.querySelectorAll('button,a,[role="button"]').forEach(el=>{
    const t=(el.innerText||el.getAttribute('aria-label')||'').trim();
    if(t && visible(el) && t.length<50) out.push({tag:el.tagName,text:t,disabled:el.disabled||null});
  });
  return out.slice(0,25);
})()
""")
print("\n=== buttons ===")
print(json.dumps(btns, indent=1)[:1000])

# any masked key shown?
masked = d.execute_script(r"""
const txt=document.body.innerText||'';
return {
  masked:(txt.match(/[A-Za-z0-9]{2,8}\*{3,}[A-Za-z0-9]{0,6}/g)||[]).slice(0,5),
  hasYDC: txt.includes('YDC'),
  hasReveal:/reveal|show|copy|view/i.test(txt)
};
""")
print("\n=== masked key presence ===")
print(json.dumps(masked))
