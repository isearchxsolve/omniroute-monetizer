# -*- coding: utf-8 -*-
"""you.com: is an API key configured? Check the playground's key field / API Management state."""
import json
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

# Look for any input/field that holds or asks for an API key, and any "no key" messaging.
r = d.execute_script(r"""
return (function(){
  function visible(el){
    const rect = el.getBoundingClientRect();
    if(rect.width<=0 || rect.height<=0) return false;
    const st = window.getComputedStyle(el);
    return st.display!=='none' && st.visibility!=='hidden';
  }
  // all text-ish inputs
  const inputs = Array.from(document.querySelectorAll('input[type="text"],input[type="password"],input:not([type]),input[type="search"]'))
    .map(el=>({type:el.type, ph:el.placeholder||'', name:el.name||'', id:el.id||'',
               vis:visible(el), valLen:(el.value||'').length, valHead:(el.value||'').slice(0,6)}));
  // labels/headings mentioning key
  const keyText = Array.from(document.querySelectorAll('label,h1,h2,h3,h4,span,div,p'))
    .map(el=>(el.innerText||'').trim())
    .filter(t=>t && t.length<80 && /api key|apikey|x-api-key|YDC|secret|token/i.test(t))
    .slice(0,12);
  // the curl example block — does it still show the YDC_API_KEY placeholder?
  const curl = (Array.from(document.querySelectorAll('.language-bash,pre')).map(e=>e.innerText||'').join('\n'));
  const hasPlaceholder = curl.includes('YDC_API_KEY');
  return {inputs, keyText, curlHasPlaceholder: hasPlaceholder};
})()
""")
print(json.dumps(r, indent=2)[:2000])
