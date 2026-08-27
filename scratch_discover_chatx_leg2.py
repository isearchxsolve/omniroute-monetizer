# -*- coding: utf-8 -*-
"""Discover chatx's leg-2 answer-polling endpoint from the app's own JS.

Leg 1 (POST /sendchat) returned conversions_id. Chrome then polls some endpoint with
that id to fetch the streamed answer. Grep the page's scripts for the poll URL.
"""
import re
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(120)

for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        if driver.current_url.startswith("https://chatx.ai"):
            break
    except Exception:
        continue
print("on:", driver.current_url)

# inline scripts + external scripts
inline = driver.execute_script(
    "return Array.from(document.scripts).filter(s=>!s.src).map(s=>s.textContent).join('\\n');")
srcs = driver.execute_script(
    "return Array.from(document.scripts).map(s=>s.src).filter(Boolean);")

blobs = [("inline", inline)]
for src in srcs:
    try:
        txt = driver.execute_script(
            "return fetch(arguments[0]).then(r=>r.text()).catch(e=>'');", src)
    except Exception:
        txt = ""
    if txt:
        blobs.append((src, txt))

print("blobs:", len(blobs))
hits = set()
for name, txt in blobs:
    for kw in ("conversions_id", "ass_conversions_id", "getchat", "getresponse",
               "poll", "setInterval", "setTimeout", "/chat", "response", "answer"):
        for m in re.finditer(re.escape(kw), txt):
            start = max(0, m.start() - 100)
            end = min(len(txt), m.end() + 180)
            seg = txt[start:end]
            if any(c in seg for c in ("url", "ajax", "fetch", "$.get", "$.post", "XMLHttpRequest", "conversions")):
                hits.add(seg)

print("\n=== HITS (%d) ===" % len(hits))
for s in sorted(hits):
    print("-" * 40)
    print(s)
