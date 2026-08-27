# -*- coding: utf-8 -*-
"""Read-only wall attribution: which video tab shows 'Insufficient credits'?
Targeted element probe only (no body.innerText -- hangs Flow's WebGL page)."""
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TARGETS = {"labs.google": "labs.google", "nemovideo.com": "nemovideo.com"}

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(15)

JS = r"""
return (() => {
  const sel = '[role="dialog"],[role="alertdialog"],[class*="modal" i],[class*="Modal"],[class*="toast" i],[class*="credit" i],[class*="quota" i],[class*="paywall" i],[class*="upgrade" i],[class*="billing" i],h1,h2,h3';
  const els = Array.from(document.querySelectorAll(sel)).slice(0, 60);
  const texts = els.map(e => (e.textContent || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
  const wallRe = /insufficient credits|out of credits|upgrade your plan|no credits|credits? (remaining|left)|run out of credits/i;
  const hits = texts.filter(t => wallRe.test(t)).map(t => t.slice(0, 160));
  // also grab any credit-counter-looking small strings
  const counters = texts.filter(t => /\d+\s*(credits?|tokens?|generations?)/i.test(t)).map(t => t.slice(0, 80));
  return JSON.stringify({ url: location.href, wallHits: hits.slice(0, 6), counters: counters.slice(0, 6) });
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
            print("### %s  (%s)" % (seat_host, info.get("url", "?")[:70]))
            if info.get("error"):
                print("  error:", info["error"])
            print("  wallHits:", info.get("wallHits") or "(none)")
            print("  counters:", info.get("counters") or "(none)")
            break
