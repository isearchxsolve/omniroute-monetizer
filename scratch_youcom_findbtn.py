# -*- coding: utf-8 -*-
"""you.com: locate the exact 'Create new key' element and its tag/attrs."""
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
if "api-keys" not in d.current_url:
    d.get("https://you.com/platform/api-keys")
    time.sleep(4)

r = d.execute_script(r"""
return (function(){
  const out=[];
  // walk ALL elements, find any whose text contains 'Create new key'
  const all=Array.from(document.querySelectorAll('*'));
  for(const el of all){
    const own=Array.from(el.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent.trim()).join(' ');
    if(/create new key/i.test(own)){
      const rect=el.getBoundingClientRect();
      out.push({
        tag:el.tagName,
        cls:(el.className&&el.className.toString)?el.className.toString().slice(0,60):'',
        id:el.id||'',
        role:el.getAttribute('role')||'',
        type:el.getAttribute('type')||'',
        text:own.slice(0,40),
        rect:[Math.round(rect.x),Math.round(rect.y),Math.round(rect.width),Math.round(rect.height)],
        clickable: el.tagName==='BUTTON'||el.tagName==='A'||el.getAttribute('role')==='button'||el.onclick!==null
      });
    }
  }
  return out;
})()
""")
print(json.dumps(r, indent=1))
