"""Select the xxpertcomments@gmail.com account on the Google chooser and complete t3.chat login."""
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

    # Find the Google accounts page
    page = None
    for pg in ctx.pages:
        if "accounts.google.com" in pg.url:
            page = pg
            break
    if page is None:
        print("No Google accounts page found")
        browser.close()
        sys.exit(1)

    print("Google accounts URL:", page.url[:100])
    body = page.locator("body").inner_text(timeout=8000)[:800]
    print("body:", body.replace("\n", " | ")[:600])

    # Click the xxpertcomments account (div with the email)
    clicked = False
    # Try data-email attribute first
    try:
        loc = page.locator("[data-email*='xxpertcomments']").first
        if loc.is_visible(timeout=3000):
            loc.click(timeout=5000)
            print("clicked [data-email*=xxpertcomments]")
            clicked = True
    except Exception:
        pass
    if not clicked:
        # Try the div containing the email text
        try:
            loc = page.locator("div:has-text('xxpertcomments@gmail.com')").first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print("clicked div:has-text('xxpertcomments@gmail.com')")
                clicked = True
        except Exception:
            pass
    if not clicked:
        # Fallback: click the div with class VV3oRb that contains the email
        try:
            loc = page.locator("div.VV3oRb:has-text('xxpertcomments')").first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print("clicked div.VV3oRb:has-text('xxpertcomments')")
                clicked = True
        except Exception:
            pass
    if not clicked:
        print("!! could not find account element")
        browser.close()
        sys.exit(1)

    # Wait for the flow to proceed (consent page or redirect back)
    time.sleep(5)
    print("\n=== pages after account click ===")
    for i, pg in enumerate(ctx.pages):
        try:
            print(f"  page {i}: {pg.url[:130]}")
        except Exception as e:
            print(f"  page {i}: err {e}")

    # If consent page, click Continue/Allow
    for pg in ctx.pages:
        if "accounts.google.com" in pg.url:
            try:
                body2 = pg.locator("body").inner_text(timeout=5000)[:800]
                print("\nconsent body:", body2.replace("\n", " | ")[:600])
                # Click Continue / Allow
                for sel in ["button:has-text('Continue')", "button:has-text('Allow')",
                            "button:has-text('Continue as')"]:
                    try:
                        loc = pg.locator(sel).first
                        if loc.is_visible(timeout=3000):
                            loc.click(timeout=5000)
                            print(f"clicked consent: {sel}")
                            break
                    except Exception:
                        continue
            except Exception as e:
                print("consent err:", e)

    time.sleep(5)
    print("\n=== final pages ===")
    for i, pg in enumerate(ctx.pages):
        try:
            print(f"  page {i}: {pg.url[:130]}")
        except Exception as e:
            print(f"  page {i}: err {e}")

    # Check t3.chat cookies for strong auth
    print("\n=== t3.chat cookies ===")
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".").lower()
        if "t3.chat" in dom:
            print(f"  {c['name']:40s} len={len(c['value'])} httpOnly={c.get('httpOnly')}")

    browser.close()
