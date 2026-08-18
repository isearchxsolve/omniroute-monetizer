"""Recon: dump current page state for t3.chat after login click, to design selectors."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
PORT = 9223
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]
    for i, pg in enumerate(ctx.pages):
        try:
            url = pg.url
            title = pg.title()
            print(f"\n=== page {i}: {url} | title={title!r} ===")
            if "accounts.google.com" in url:
                print("  -> GOOGLE ACCOUNTS PAGE")
                body = pg.locator("body").inner_text(timeout=5000)[:1500]
                print("  body:", body.replace("\n", " | ")[:1200])
            elif "t3.chat" in url:
                body = pg.locator("body").inner_text(timeout=5000)[:1500]
                print("  body:", body.replace("\n", " | ")[:1200])
                btns = pg.evaluate(
                    """() => Array.from(document.querySelectorAll('button, a, [role=button]'))
                        .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())
                        .filter(t => t && t.length < 60).slice(0, 40)"""
                )
                print("  buttons/links:", btns)
        except Exception as e:
            print(f"  page {i} error: {e}")
    browser.close()
