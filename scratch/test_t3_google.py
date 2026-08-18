"""Test: click 'Continue with Google' on t3.chat login page, handle Google chooser."""
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
    page = None
    for pg in ctx.pages:
        if "t3.chat" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()
    page.goto("https://t3.chat/auth/login", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    print("URL:", page.url)
    print("title:", page.title())

    # Click Continue with Google
    try:
        page.locator("button:has-text('Continue with Google')").first.click(timeout=6000)
        print("clicked Continue with Google")
    except Exception as e:
        print("click err:", e)
    time.sleep(5)
    print("URL after click:", page.url)

    # If on accounts.google.com, dump
    if "accounts.google.com" in page.url:
        print("ON GOOGLE ACCOUNTS")
        body = page.locator("body").inner_text(timeout=5000)[:1500]
        print("body:", body.replace("\n", " | ")[:1200])
    else:
        # maybe popup
        print("pages:", [pg.url[:80] for pg in ctx.pages])
        for pg in ctx.pages:
            if "accounts.google.com" in pg.url:
                print("POPUP on accounts.google.com")
                body = pg.locator("body").inner_text(timeout=5000)[:1500]
                print("body:", body.replace("\n", " | ")[:1200])
    browser.close()
