# -*- coding: utf-8 -*-
"""Find the XJ base-path constant and stream_key consumption in felo JS."""
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

xj_hits = set()
sk_hits = set()
for src in srcs:
    try:
        txt = driver.execute_script(
            "return fetch(arguments[0]).then(r=>r.text()).catch(e=>'');", src)
    except Exception:
        txt = ""
    if not txt:
        continue
    # XJ constant definition: e.g. XJ:"/api-proxy/main" or XJ="/api-proxy/main"
    for m in re.finditer(r"XJ\s*[:=]\s*[\"'`]([^\"'`]+)[\"'`]", txt):
        xj_hits.add(m.group(1))
    # stream_key used in a URL or fetch
    for m in re.finditer(r".{60}stream_key.{120}", txt):
        s = m.group(0)
        if "fetch" in s or "url" in s.lower() or "resume" in s.lower() or "get(" in s.lower():
            sk_hits.add(s)

print("=== XJ values ===")
for v in sorted(xj_hits):
    print(" ", v)
print("\n=== stream_key usage (%d) ===" % len(sk_hits))
for s in sorted(sk_hits)[:20]:
    print(" ", s[:200])
