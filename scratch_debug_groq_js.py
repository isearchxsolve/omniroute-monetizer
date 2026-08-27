# -*- coding: utf-8 -*-
"""Debug step 3: dump the exact module JS and test sub-expressions."""
import sys
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import selenium_browser_replay as sbr

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

js, header = sbr.LIVE_BEARER_RULES["groq"]
print("=== JS as stored ===")
print(repr(js[:200]))
print("...")

# test 1: run as-is with return prefix
try:
    r1 = driver.execute_script("return " + js)
    print("test1 (return + IIFE):", type(r1), str(r1)[:40] if r1 else None)
except Exception as e:
    print("test1 EXCEPTION:", e)

# test 2: wrap in a function explicitly
try:
    r2 = driver.execute_script("var f = " + js.strip() + "; return f;")
    print("test2 (var f = IIFE):", type(r2), str(r2)[:40] if r2 else None)
except Exception as e:
    print("test2 EXCEPTION:", e)

# test 3: minimal IIFE
try:
    r3 = driver.execute_script("return (function(){ var m = document.cookie.match(/(?:^|;\\s*)stytch_session_jwt=([^;]+)/); return m ? m[1] : 'NOMATCH'; })()")
    print("test3 (minimal IIFE):", type(r3), str(r3)[:40] if r3 else None)
except Exception as e:
    print("test3 EXCEPTION:", e)
