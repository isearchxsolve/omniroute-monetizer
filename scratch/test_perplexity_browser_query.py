"""Shallow check: can the logged-in Free Perplexity account actually answer
in the browser? Submit a real query and observe the response."""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 9223

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    page = None
    for pg in ctx.pages:
        if "perplexity.ai" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()

    page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    print(f"URL: {page.url[:120]}")

    # Find the main search/ask textarea
    box = None
    for sel in ["textarea", "[contenteditable='true']", "div[role='textbox']",
                "input[type='text']", "[data-testid*='ask']"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                box = loc
                print(f"found input: {sel}")
                break
        except Exception:
            continue

    if box is None:
        print("!! no input box found")
        # dump visible text
        body = page.evaluate("() => document.body ? document.body.innerText.slice(0,400) : ''")
        print(f"body: {body[:300]!r}")
        browser.close()
        sys.exit(1)

    try:
        box.click(timeout=5000)
        box.fill("What is 2+2? Answer with just the number.", timeout=5000)
        page.wait_for_timeout(1000)
        # submit
        page.keyboard.press("Enter")
        print("submitted query")
    except Exception as e:
        print(f"input err: {e}")
        try:
            box.type("What is 2+2? Answer with just the number.", delay=30)
            page.keyboard.press("Enter")
            print("submitted via type")
        except Exception as e2:
            print(f"type err: {e2}")

    # wait for response
    page.wait_for_timeout(12000)
    print(f"after submit URL: {page.url[:120]}")
    body = page.evaluate("() => document.body ? document.body.innerText.slice(0,800) : ''")
    print(f"--- page text ---\n{body[:700]}")

    browser.close()
