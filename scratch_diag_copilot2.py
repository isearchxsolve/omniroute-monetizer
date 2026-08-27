# -*- coding: utf-8 -*-
"""Check copilot tab state after the failed re-test: did the 2nd prompt send?"""
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
        if "copilot.microsoft.com" in (driver.current_url or ""):
            break
    except Exception:
        continue

JS = r"""
try {
  const userMsgs = Array.from(document.querySelectorAll('[data-content="user-message"]'))
    .map(e=>(e.innerText||'').replace(/\s+/g,' ').slice(0,60));
  const aiBodies = Array.from(document.querySelectorAll('[data-testid="ai-message-body"]'))
    .map(e=>(e.innerText||'').replace(/\s+/g,' ').slice(0,60));
  const ta = document.querySelector('textarea#userInput');
  const stopBtn = document.querySelector('[data-testid="stop-button"],button[aria-label*="Stop"]');
  return JSON.stringify({
    url: location.href,
    userMsgCount: userMsgs.length,
    userMsgs: userMsgs.slice(-4),
    aiBodyCount: aiBodies.length,
    aiBodies: aiBodies.slice(-4),
    composerValue: ta ? ta.value.slice(0,60) : '(no textarea)',
    stopVisible: !!stopBtn
  }, null, 1);
} catch(e){ return 'ERR '+String(e); }
"""
print(driver.execute_script(JS))
