# -*- coding: utf-8 -*-
"""List ALL copilot.microsoft.com tabs and whether each has a chat composer."""
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(20)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
    except Exception:
        continue
    u = driver.current_url or ""
    if "copilot.microsoft.com" not in u:
        continue
    try:
        info = driver.execute_script(r"""
        try {
          function visible(el){
            const r = el.getBoundingClientRect();
            if(r.width<=0||r.height<=0) return false;
            const st = window.getComputedStyle(el);
            return st.display!=='none' && st.visibility!=='hidden';
          }
          const ta = Array.from(document.querySelectorAll('textarea')).find(el=>visible(el));
          return JSON.stringify({
            hasComposer: !!ta,
            composerId: ta ? (ta.id||'(noid)') : '',
            userMsgs: document.querySelectorAll('[data-content="user-message"]').length,
            aiBodies: document.querySelectorAll('[data-testid="ai-message-body"]').length
          });
        } catch(e){ return JSON.stringify({error:String(e)}); }
        """)
        print(u[:90], "->", info)
    except Exception as e:
        print(u[:90], "-> EXC", e)
