# -*- coding: utf-8 -*-
"""Full-DOM wall attribution using textContent (safe: no reflow, unlike innerText).
Searches for the exact wall phrase the operator reported."""
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TARGETS = {"labs.google": "labs.google", "nemovideo.com": "nemovideo.com"}
WALL = "insufficient credits"

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(20)

JS = r"""
return (() => {
  const t = (document.body ? document.body.textContent : '') || '';
  const lower = t.toLowerCase();
  const idx = lower.indexOf('insufficient credits');
  const idx2 = lower.indexOf('run out of credits');
  const idx3 = lower.indexOf('upgrade your plan');
  const hit = idx >= 0 ? idx : (idx2 >= 0 ? idx2 : idx3);
  const ctx = hit >= 0 ? t.slice(Math.max(0, hit - 80), hit + 160).replace(/\s+/g, ' ') : '';
  // credit counters anywhere
  const m = t.match(/(\d[\d,]*)\s*(?:credits?|credits remaining)/gi) || [];
  return JSON.stringify({ url: location.href, wallFound: hit >= 0, context: ctx, counters: m.slice(0, 5) });
})()
"""

seen = set()
for seat_host, substr in TARGETS.items():
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
            try:
                info = json.loads(driver.execute_script(JS) or "{}")
            except Exception as e:
                info = {"error": str(e)[:120]}
            print("### %s" % seat_host)
            print("  url:", info.get("url", "?")[:80])
            print("  wallFound:", info.get("wallFound"))
            if info.get("context"):
                print("  context:", info["context"])
            print("  counters:", info.get("counters") or "(none)")
            if info.get("error"):
                print("  error:", info["error"])
            break
