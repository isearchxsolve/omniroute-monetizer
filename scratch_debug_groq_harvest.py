# -*- coding: utf-8 -*-
"""Debug: run the exact LIVE_BEARER_RULES groq JS via the main tool's code path."""
import sys
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import selenium_browser_replay as sbr

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
print("attached, windows=%d" % len(driver.window_handles))

# find console tab like the main tool does
handle = None
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if driver.current_url.startswith("https://console.groq.com"):
            handle = h
            break
    except Exception:
        continue
print("console tab handle:", handle, driver.current_url if handle else None)

js, header = sbr.LIVE_BEARER_RULES["groq"]
tok = driver.execute_script("return " + js)
print("token type:", type(tok), "value:", (str(tok)[:30] + "...") if tok else None)

# also try the wrapper function directly
hdrs, src = sbr.harvest_live_bearer(driver, "api.groq.com", {"authorization": "Bearer stale"})
print("harvest_live_bearer ->", src, hdrs["authorization"][:40])
