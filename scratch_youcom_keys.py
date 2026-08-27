# -*- coding: utf-8 -*-
"""you.com: navigate to API Keys management and report whether a key exists (never print it)."""
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

print("current url:", d.current_url)

# Find a link/button to API keys management
links = d.execute_script(r"""
return (function(){
  function visible(el){
    const r=el.getBoundingClientRect();
    if(r.width<=0||r.height<=0) return false;
    const st=getComputedStyle(el);
    return st.display!=='none'&&st.visibility!=='hidden';
  }
  const out=[];
  document.querySelectorAll('a,button,[role="link"],[role="tab"],[role="menuitem"]').forEach(el=>{
    const t=(el.innerText||el.getAttribute('aria-label')||'').trim();
    if(t && /api key|keys|dashboard|account|billing|settings|console/i.test(t) && visible(el)){
      out.push({tag:el.tagName, text:t.slice(0,40), href:el.href||null});
    }
  });
  return out.slice(0,20);
})()
""")
print("=== candidate nav links ===")
print(json.dumps(links, indent=1)[:1200])

# Try navigating to the likely API keys dashboard URL
for url in ["https://you.com/platform/dashboard", "https://you.com/dashboard", "https://api.you.com/dashboard"]:
    try:
        d.get(url)
        time.sleep(3)
        print(f"\nnavigated -> {url}")
        print("final url:", d.current_url)
        body = d.execute_script("return (document.body.innerText||'').slice(0,600)")
        print("body head:", body.replace("\n"," | ")[:400])
        # look for key-like masked values
        keys = d.execute_script(r"""
        return (function(){
          const txt=document.body.innerText||'';
          const masked=txt.match(/[A-Za-z0-9_-]{4,8}\*{3,}[A-Za-z0-9_-]{0,6}/g)||[];
          const hasCreate=/create|generate|new key|add key/i.test(txt);
          return {maskedCount:masked.length, maskedSample:masked.slice(0,3), hasCreate};
        })()
        """)
        print("key presence:", json.dumps(keys))
        if keys.get("maskedCount") or keys.get("hasCreate"):
            print(">>> FOUND key management surface at", url)
            break
    except Exception as e:
        print(f"  nav {url} failed: {e}")
