# -*- coding: utf-8 -*-
"""Diagnose chatgpt.com sign-in state in the automation browser (port 9222).

Opens ONE new tab to chatgpt.com, waits for load, then reports whether the page shows
a signed-in chat UI or a login wall. Takes a screenshot for visual verification.
NEVER calls driver.quit() (operator's working browser). Attaches via debuggerAddress.
"""
import time, pathlib, json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT = pathlib.Path("state/reauth_screenshots")
OUT.mkdir(parents=True, exist_ok=True)

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(60)

orig = driver.current_window_handle
driver.switch_to.new_window("tab")
tab = driver.current_window_handle
try:
    driver.get("https://chatgpt.com/")
    time.sleep(8)  # let the SPA hydrate
    url = driver.current_url
    title = driver.title
    raw = driver.execute_script(r"""
    try {
      const body = document.body ? document.body.innerText : '';
      const promptTa = !!document.querySelector('textarea#prompt-textarea, div#prompt-textarea[contenteditable="true"], textarea[placeholder*="Ask" i]');
      const loginBtn = !!Array.from(document.querySelectorAll('button,a')).find(el=>/log ?in|sign ?in|continue with/i.test(el.innerText||'') && el.offsetParent!==null);
      const avatar = !!document.querySelector('img[alt*="avatar" i], [data-testid*="profile" i], button[aria-label*="profile" i]');
      return JSON.stringify({url: location.href, hasPrompt: promptTa, hasLoginCta: loginBtn, hasAvatar: avatar, bodySnippet: body.slice(0,400).replace(/\s+/g,' ')});
    } catch(e) { return JSON.stringify({error: String(e)}); }
    """)
    info = json.loads(raw) if raw else {"error": "empty script result"}
    print("URL:", url)
    print("TITLE:", title)
    print(json.dumps(info, indent=1))
    shot = OUT / "chatgpt_signin_check.png"
    driver.save_screenshot(str(shot))
    print("screenshot:", shot)
    if info.get("hasPrompt") and not info.get("hasLoginCta"):
        print("VERDICT: SIGNED_IN (chat input present, no login CTA)")
    elif info.get("hasLoginCta"):
        print("VERDICT: LOGIN_WALL")
    else:
        print("VERDICT: UNCLEAR (inspect screenshot)")
finally:
    # close only the tab WE opened, return focus to the original window
    try:
        driver.close()
    except Exception:
        pass
    try:
        driver.switch_to.window(orig)
    except Exception:
        pass
    # NOTE: no driver.quit() — this is the operator's working browser
