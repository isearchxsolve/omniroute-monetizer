# -*- coding: utf-8 -*-
"""you.com probe v4: find the SUBMIT button near the query textarea (geometry + content)."""
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(30)

for h in d.window_handles:
    try:
        d.switch_to.window(h)
        if "you.com" in d.current_url:
            break
    except Exception:
        continue
else:
    raise SystemExit("NO you.com tab")

r = d.execute_script(r"""
return (function(){
  function visible(el){
    const r = el.getBoundingClientRect();
    if(r.width<=0 || r.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  const ta = Array.from(document.querySelectorAll('textarea')).find(e=>visible(e));
  if(!ta) return {err:'no visible textarea'};
  const tr = ta.getBoundingClientRect();
  const cx = tr.x+tr.width/2, cy = tr.y+tr.height/2;
  const btns = Array.from(document.querySelectorAll('button,[role="button"]'))
    .filter(visible).map(el=>{
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName,
        al: el.getAttribute('aria-label')||'',
        dt: el.getAttribute('data-testid')||'',
        ty: el.getAttribute('type')||'',
        dis: el.disabled,
        txt: (el.innerText||'').replace(/\s+/g,' ').trim().slice(0,30),
        svg: el.querySelector('svg')? 'Y':'',
        cls: ((el.className&&el.className.baseVal!==undefined)?el.className.baseVal:(el.className||'')+'').slice(0,50),
        dist: Math.round(Math.hypot(r.x+r.width/2-cx, r.y+r.height/2-cy)),
        w: Math.round(r.width), h: Math.round(r.height)
      };
    }).sort((a,b)=>a.dist-b.dist);
  return {ta:{id:ta.id, ph:ta.placeholder, x:Math.round(tr.x), y:Math.round(tr.y), w:Math.round(tr.width), h:Math.round(tr.height)},
          buttonsByDist: btns.slice(0,12)};
})()
""")
print(json.dumps(r, indent=2))
