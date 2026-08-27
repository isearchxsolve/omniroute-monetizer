# -*- coding: utf-8 -*-
"""Discover felo's leg-2 (message_center_v1) endpoint from the app's own JS bundles.

Doctrine: reproduce what Chrome does. The page's JS contains the exact endpoint it polls
with the stream_key. Grep the loaded script sources for 'message_center' / 'stream_key'.
"""
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(120)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if driver.current_url.startswith("https://felo.ai"):
            break
    except Exception:
        continue
print("on:", driver.current_url)

# collect all script srcs
srcs = driver.execute_script(
    "return Array.from(document.scripts).map(s=>s.src).filter(Boolean);")
print("script count:", len(srcs))

hits = set()
for src in srcs:
    try:
        txt = driver.execute_script(
            "return fetch(arguments[0]).then(r=>r.text()).catch(e=>'');", src)
    except Exception:
        txt = ""
    if not txt:
        continue
    for m in re.finditer(r"[\"'`][^\"'`]{0,80}(?:message_center|stream_key|/messages|/question|/answer)[^\"'`]{0,80}[\"'`]", txt):
        hits.add(m.group(0))
    # also look for URL path templates
    for m in re.finditer(r"[\"'`]/api-proxy/[^\"'`]{0,120}[\"'`]", txt):
        hits.add(m.group(0))

print("\n=== HITS (%d) ===" % len(hits))
for h in sorted(hits):
    print(h)
