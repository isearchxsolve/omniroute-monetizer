# -*- coding: utf-8 -*-
"""Bring the Hugging Face tab to the front on seat1 Chrome (:9222) for operator
verification of the 402 'depleted monthly credits' claim (Chrome Gap Doctrine,
class (b) proof requires reproduction in Chrome observed by the operator).
Attaches via debuggerAddress only — never launches, never quits."""
import sys, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

PORT = 9222
opts = Options()
opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT}")
driver = webdriver.Chrome(options=opts)
driver.set_script_timeout(30)
print(f"attached, windows={len(driver.window_handles)}", flush=True)

target = None
for h in driver.window_handles:
    try:
        driver.switch_to.window(h)
        u = driver.current_url or ""
    except Exception:
        continue
    if "huggingface.co" in u:
        target = (h, u)
        break

if target is None:
    # No HF tab: open one in a new tab (Selenium new_window is not popup-blocked).
    driver.switch_to.new_window("tab")
    driver.get("https://huggingface.co/chat/")
    time.sleep(4)
    print("OPENED NEW TAB:", driver.current_url, flush=True)
else:
    h, u = target
    driver.switch_to.window(h)
    try:
        driver.execute_cdp_cmd("Page.bringToFront", {})
    except Exception as e:
        print("bringToFront note:", str(e)[:80], flush=True)
    # Make sure we are on the chat app, not a model page.
    if "/chat" not in u:
        driver.get("https://huggingface.co/chat/")
        time.sleep(4)
    print("FOCUSED EXISTING TAB:", driver.current_url, flush=True)

try:
    title = driver.title
except Exception:
    title = "?"
print("title:", title, flush=True)
print("DONE - tab is in front on seat1. Do NOT quit; operator will inspect.", flush=True)
