# -*- coding: utf-8 -*-
"""Debug step 2: what does document.cookie contain on the console tab right now?"""
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if driver.current_url.startswith("https://console.groq.com"):
            break
    except Exception:
        continue

print("url:", driver.current_url)
cookie = driver.execute_script("return document.cookie")
names = [c.strip().split("=")[0] for c in cookie.split(";")]
print("cookie names:", names)
print("has stytch_session_jwt:", "stytch_session_jwt" in names)
m = driver.execute_script(
    "var m = document.cookie.match(/(?:^|;\\s*)stytch_session_jwt=([^;]+)/); return m ? m[1].length : -1;")
print("regex match length:", m)
