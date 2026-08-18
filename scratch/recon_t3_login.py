"""Recon t3.chat login modal: click Login, dump what appears."""
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
        page.goto("https://t3.chat", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

    # Click Login
    try:
        page.locator("button:has-text('Login'), a:has-text('Login')").first.click(timeout=5000)
        print("clicked Login")
    except Exception as e:
        print("login click err:", e)
    time.sleep(3)

    print("URL now:", page.url)
    body = page.locator("body").inner_text(timeout=5000)[:2000]
    print("body:", body.replace("\n", " | ")[:1500])
    btns = page.evaluate(
        """() => Array.from(document.querySelectorAll('button, a, [role=button], [role=dialog] *'))
            .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())
            .filter(t => t && t.length < 60).slice(0, 60)"""
    )
    print("buttons/links:", btns)
    # Check for iframes (Google sign-in often in iframe)
    frames = page.frames
    print("frames:", [f.url[:80] for f in frames])
    browser.close()
