# -*- coding: utf-8 -*-
"""PROOF OF THESIS: the provider's adapter (the 'smell') lives IN the page as callable code.

Chrome doesn't know what deepseek wants. Deepseek's own JS does. This script attaches to
seat1, lists open provider tabs, then for the deepseek tab locates its own request-building /
PoW / signing code in the loaded scripts -- demonstrating the knowledge is present and
executable in-page, so replay should RE-INVOKE it, not rebuild the bytes.

Attach-only via debuggerAddress. NEVER calls driver.quit(). Read-only: no requests fired.
"""
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

opts = Options()
opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(120)

# ---- 1. list open tabs ----
tabs = []
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        tabs.append((h, driver.current_url))
    except Exception:
        pass

print("=== OPEN TABS (%d) ===" % len(tabs))
for h, u in tabs:
    print("  %s" % u[:110])

# ---- 2. pick the deepseek tab ----
target = None
for h, u in tabs:
    if "deepseek" in u:
        target = (h, u)
        break

if not target:
    print("\nno deepseek tab open; thesis demo needs that tab. Listing candidate providers:")
    for h, u in tabs:
        print("  ", u.split("/")[2] if "://" in u else u)
    raise SystemExit(0)

h, u = target
driver.switch_to.window(h)
driver.execute_cdp_cmd("Page.bringToFront", {})
print("\n=== ON DEEPSEEK TAB ===\n", u)

# ---- 3. gather loaded code ----
inline = driver.execute_script(
    "return Array.from(document.scripts).filter(s=>!s.src).map(s=>s.textContent).join('\\n');")
srcs = driver.execute_script(
    "return Array.from(document.scripts).map(s=>s.src).filter(Boolean);")
print("inline script chars:", len(inline), "| external scripts:", len(srcs))

blobs = [("inline", inline)]
for src in srcs:
    try:
        txt = driver.execute_script(
            "return fetch(arguments[0]).then(r=>r.text()).catch(e=>'');", src)
    except Exception:
        txt = ""
    if txt:
        blobs.append((src.split("/")[-1][:40], txt))

# ---- 4. hunt for the ADAPTER: the code that builds/sends the chat request ----
# These are the 'smell' keywords: PoW / challenge / signing / send construction.
KEYWORDS = ["challenge", "pow", "nonce", "sign", "x-sign", "encrypt",
            "chat/completions", "send", "fetch(", "XMLHttpRequest",
            "authorization", "Bearer", "token"]

print("\n=== ADAPTER EVIDENCE (the knowledge Chrome 'smells' is HERE, in-page) ===")
seen = set()
count = 0
for name, txt in blobs:
    for kw in KEYWORDS:
        for m in re.finditer(re.escape(kw), txt, re.IGNORECASE):
            start = max(0, m.start() - 90)
            end = min(len(txt), m.end() + 160)
            seg = txt[start:end].replace("\n", " ")
            key = seg[:60]
            if key in seen:
                continue
            seen.add(key)
            # only keep segments that look like real request/adapter logic
            if any(c in seg for c in ("fetch", "ajax", "XMLHttp", "sign", "challenge",
                                      "pow", "nonce", "encrypt", "Bearer", "completions")):
                print("\n[%s] kw=%r" % (name, kw))
                print("  ..." + seg + "...")
                count += 1
                if count >= 25:
                    break
        if count >= 25:
            break
    if count >= 25:
        break

print("\n=== TOTAL adapter-code fragments surfaced: %d ===" % count)
print("THESIS: this code is the provider's adapter. Chrome just runs it.")
print("DONE - do NOT quit.")
