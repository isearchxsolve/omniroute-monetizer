"""Click Continue with Google on t3.chat, then select the xxpertcomments account on Google."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
PORT = 9223
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    # Find the t3.chat page
    page = None
    for pg in ctx.pages:
        if "t3.chat" in pg.url or "signin.t3.chat" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()
        page.goto("https://t3.chat/auth/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

    print("current URL:", page.url)

    # Click the Google anchor (it's an <a> with href /api/login?provider=GoogleOAuth)
    try:
        page.locator("a:has-text('Continue with Google')").first.click(timeout=6000)
        print("clicked Continue with Google (anchor)")
    except Exception as e:
        print("click err:", e)

    # Wait and check for popup or navigation
    time.sleep(5)
    print("\n=== pages after click ===")
    for i, pg in enumerate(ctx.pages):
        try:
            print(f"  page {i}: {pg.url[:130]}")
        except Exception as e:
            print(f"  page {i}: err {e}")

    # If a popup opened on accounts.google.com, handle it
    for pg in ctx.pages:
        if "accounts.google.com" in pg.url:
            print("\nFOUND Google accounts popup:", pg.url[:130])
            body = pg.locator("body").inner_text(timeout=8000)[:2000]
            print("body:", body.replace("\n", " | ")[:1500])
            # Click the xxpertcomments account
            try:
                pg.locator("div[data-email*='xxpertcomments'], div[data-email*='gmail.com']").first.click(timeout=5000)
                print("clicked account element")
            except Exception as e:
                print("account click err:", e)
            time.sleep(3)
            print("after account click URL:", pg.url)
            break

    browser.close()
