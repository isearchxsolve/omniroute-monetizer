# -*- coding: utf-8 -*-
"""Open aymo, chathub, veoaifree chat UIs on seat1 (:9222) for operator verification.

Doctrine class-(b) proof step: the operator must see the same quota wall in Chrome
itself. Attach-only via debuggerAddress. NEVER calls driver.quit().
"""
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TARGETS = [
    ("aymo", "https://aymo.ai/"),
    ("chathub", "https://app.chathub.gg/"),
    ("veoaifree", "https://veoaifree.com/"),
]


def main() -> int:
    opts = Options()
    opts.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    driver = webdriver.Chrome(options=opts)
    print("attached, windows=%d" % len(driver.window_handles))

    opened = []
    for name, url in TARGETS:
        # reuse an existing tab on that host if one exists
        found = None
        for h in driver.window_handles:
            try:
                driver.switch_to.window(h)
                if name.replace("veoaifree", "veoaifree") in driver.current_url or \
                   (name == "chathub" and "chathub.gg" in driver.current_url) or \
                   (name == "aymo" and "aymo.ai" in driver.current_url):
                    found = h
                    break
            except Exception:
                continue
        if found is None:
            driver.switch_to.new_window("tab")
            driver.get(url)
            time.sleep(3)
            print("OPENED NEW TAB %s: %s" % (name, url))
        else:
            driver.switch_to.window(found)
            driver.execute_cdp_cmd("Page.bringToFront", {})
            print("REUSED TAB %s: %s" % (name, driver.current_url))
        opened.append((name, driver.current_url))

    # bring the FIRST target (aymo) to the very front so operator starts there
    for h in driver.window_handles:
        try:
            driver.switch_to.window(h)
            if "aymo.ai" in driver.current_url:
                driver.execute_cdp_cmd("Page.bringToFront", {})
                break
        except Exception:
            continue

    print("---")
    for name, u in opened:
        print("  %s -> %s" % (name, u))
    print("DONE - all three tabs open on seat1, aymo in front. Do NOT quit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
