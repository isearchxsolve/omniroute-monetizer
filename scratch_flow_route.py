# -*- coding: utf-8 -*-
"""Fast targeted probe: find the Flow project/generate route (hrefs + clickable project tiles)."""
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(15)

JS = r"""
try {
  const hrefs = Array.from(document.querySelectorAll('a[href]'))
    .map(a=>a.getAttribute('href')).filter(h=>h && /project|flow|generate|fx/i.test(h));
  const uniq = Array.from(new Set(hrefs)).slice(0,20);
  // also grab any element whose aria-label mentions project/generate
  const labeled = Array.from(document.querySelectorAll('[aria-label]'))
    .map(e=>e.getAttribute('aria-label')).filter(l=>/project|generate|new|create/i.test(l||'')).slice(0,15);
  return JSON.stringify({hrefs:uniq, labeled:labeled, url:location.href});
} catch(e){ return JSON.stringify({error:String(e)}); }
"""

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
    except Exception:
        continue
    if "labs.google" in (driver.current_url or ""):
        info = json.loads(driver.execute_script(JS) or "{}")
        print("url:", info.get("url"))
        print("hrefs:")
        for x in info.get("hrefs", []):
            print("   ", x)
        print("aria-labels:")
        for x in info.get("labeled", []):
            print("   ", x)
        break
