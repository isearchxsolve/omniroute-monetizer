# -*- coding: utf-8 -*-
"""you.com: extract the authoritative curl example from the playground page (redact key)."""
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

d.get("https://you.com/platform/playground/answer")
time.sleep(4)
print("on:", d.current_url)

# grab all code blocks / pre text
blocks = d.execute_script(r"""
return Array.from(document.querySelectorAll('pre,code,.language-bash,[class*="code" i]'))
  .map(e=>(e.innerText||'').trim())
  .filter(t=>t && t.length>10);
""")
for i, b in enumerate(blocks):
    print(f"--- block {i} ---")
    print(b[:600])
    print()
