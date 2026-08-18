"""Blackbox click-through login: GOOGLE button -> account chooser -> consent.

Blueprint: docs/GOOGLE_SSO_LOGIN_BLUEPRINT.md
Strong cookie target: __Secure-authjs.session-token (or authjs.session-token).
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 9223
STRONG = ["__Secure-authjs.session-token", "authjs.session-token"]


def handle_google(page):
    if "accounts.google.com" not in page.url:
        return False
    print(f"  [google] on {page.url[:80]}")
    for sel in ["[data-email*='xxpertcomments']",
                "div:has-text('xxpertcomments@gmail.com')",
                "div.VV3oRb:has-text('xxpertcomments')"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print(f"  [google] clicked account: {sel}")
                page.wait_for_timeout(4000)
                return True
        except Exception:
            continue
    for sel in ["button:has-text('Continue')", "button:has-text('Allow')",
                "button:has-text('Continue as')"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print(f"  [google] clicked consent: {sel}")
                page.wait_for_timeout(4000)
                return True
        except Exception:
            continue
    return False


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    page = None
    for pg in ctx.pages:
        if "blackbox.ai" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()

    if "app.blackbox.ai/login" not in page.url:
        page.goto("https://app.blackbox.ai/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
    print(f"starting URL: {page.url[:120]}")

    # Click GOOGLE button
    clicked = False
    for sel in ["button:has-text('GOOGLE')", "button:has-text('Google')",
                "button:has-text('Continue with Google')",
                "button:has-text('Sign in with Google')"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=4000):
                loc.click(timeout=6000)
                print(f"[click] Google button: {sel}")
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        print("!! no Google button found")
        browser.close()
        sys.exit(1)

    page.wait_for_timeout(4000)
    print(f"after Google click: {page.url[:120]}")

    # Handle Google flow across all pages
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(3)
        for pg in ctx.pages:
            if "accounts.google.com" in pg.url:
                handle_google(pg)
        names = set()
        for c in ctx.cookies():
            dom = (c.get("domain") or "").lstrip(".").lower()
            if "blackbox.ai" in dom:
                names.add(c["name"])
        present = [n for n in STRONG if n in names]
        if present:
            print(f"\n[OK] SIGNED IN — strong cookies: {present}")
            browser.close()
            sys.exit(0)

    print("\ntimeout waiting for strong auth cookie")
    names = set()
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".").lower()
        if "blackbox.ai" in dom:
            names.add(c["name"])
    print(f"final blackbox cookies: {sorted(names)}")
    browser.close()
