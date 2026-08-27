# -*- coding: utf-8 -*-
"""Screenshot both video tabs to attribute the 'Insufficient credits' wall visually."""
import os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

OUT = r"d:\omniroute-monetizer\evidence"
os.makedirs(OUT, exist_ok=True)

TARGETS = {"labs_google": "labs.google", "nemovideo": "nemovideo.com"}

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)

seen = set()
for name, substr in TARGETS.items():
    for h in driver.window_handles:
        if h in seen:
            continue
        try:
            driver.switch_to.window(h)
        except Exception:
            continue
        u = driver.current_url or ""
        if substr in u:
            seen.add(h)
            time.sleep(2)
            path = os.path.join(OUT, "video_wall_%s.png" % name)
            try:
                driver.save_screenshot(path)
                print("saved:", path, "| url:", u[:80])
            except Exception as e:
                print("screenshot failed for", name, ":", str(e)[:100])
            break
