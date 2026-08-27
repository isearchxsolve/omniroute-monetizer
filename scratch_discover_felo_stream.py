# -*- coding: utf-8 -*-
"""Find consumeStream/resumeStream URL construction in felo JS."""
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
        if driver.current_url.startswith("https://felo.ai"):
            break
    except Exception:
        continue

srcs = driver.execute_script(
    "return Array.from(document.scripts).map(s=>s.src).filter(Boolean);")

hits = set()
for src in srcs:
    try:
        txt = driver.execute_script(
            "return fetch(arguments[0]).then(r=>r.text()).catch(e=>'');", src)
    except Exception:
        txt = ""
    if not txt:
        continue
    for kw in ("consumeStream", "resumeStream", "EventSource", "text/event-stream",
               "/stream", "getStreamUrl", "streamUrl"):
        for m in re.finditer(re.escape(kw), txt):
            start = max(0, m.start() - 120)
            end = min(len(txt), m.end() + 220)
            hits.add(txt[start:end])

print("=== context hits (%d) ===" % len(hits))
for s in sorted(hits):
    print("-" * 40)
    print(s)
