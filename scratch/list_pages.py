"""List all open pages in the CDP browser."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    for i, ctx in enumerate(browser.contexts):
        print(f"context {i}: {len(ctx.pages)} pages")
        for j, pg in enumerate(ctx.pages):
            try:
                print(f"  [{j}] {pg.url[:120]}")
            except Exception as e:
                print(f"  [{j}] <error {e}>")
