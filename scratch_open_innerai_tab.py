# -*- coding: utf-8 -*-
"""Open app.innerai.com in a new tab of the attached live Chrome, wait for load,
and report whether it lands signed-in or on a login wall. Replay-only: no login,
no signup, no wall-solving. If walled, report and stop."""
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
d = webdriver.Chrome(options=opts)
d.set_script_timeout(30)

# open new tab via CDP (not window.open -> not popup-blocked)
d.switch_to.new_window("tab")
d.get("https://app.innerai.com/")
time.sleep(8)
print("final url:", d.current_url)
print("title:", d.title)

JS = r"""
(function(){
  const body = (document.body && document.body.innerText || '').slice(0, 400);
  const hasInput = !!document.querySelector('textarea, [contenteditable="true"]');
  const loginHints = /sign in|log in|login|sign up|register|password/i.test(document.body.innerText.slice(0,2000));
  return {body_head: body.replace(/\s+/g,' ').slice(0,300), has_chat_input: hasInput, login_hints: loginHints};
})()
"""
r = d.execute_script("return " + JS.strip())
print("has_chat_input:", r["has_chat_input"])
print("login_hints:", r["login_hints"])
print("body_head:", r["body_head"])
print("DONE - do NOT quit.")
