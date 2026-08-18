"""Perplexity click-through login: Get started -> Google SSO -> account -> consent.

Follows the PROVEN blueprint (docs/GOOGLE_SSO_LOGIN_BLUEPRINT.md):
1. Find and click the entry button (Get started / Sign up / Log in)
2. Handle Google account chooser (select xxpertcomments)
3. Handle consent (Continue)
4. Verify strong auth cookie appears
"""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 9223
STRONG = ["__Secure-next-auth.session-token", "__Secure-perplexity_session"]


def handle_google(page):
    """Handle account chooser + consent on accounts.google.com."""
    if "accounts.google.com" not in page.url:
        return False
    print(f"  [google] on {page.url[:80]}")
    # Account chooser: click the xxpertcomments account
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
    # Consent: click Continue/Allow
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

    # Find the perplexity onboarding page
    page = None
    for pg in ctx.pages:
        if "perplexity.ai" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()
        page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

    print(f"starting URL: {page.url[:120]}")

    # Step 1: Click "Get started" or any auth entry button
    clicked = False
    for sel in ["button:has-text('Get started')", "button:has-text('Sign up')",
                "button:has-text('Log in')", "button:has-text('Sign in')",
                "a:has-text('Get started')", "a:has-text('Sign up')",
                "a:has-text('Log in')", "a:has-text('Sign in')",
                "button:has-text('Continue with Google')",
                "button:has-text('Google')"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print(f"[click] entry: {sel}")
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        # JS fallback
        r = page.evaluate(r"""() => {
            const els = Array.from(document.querySelectorAll('button, a, [role=button]'));
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if (/get started|sign up|log ?in|sign in|continue with google/i.test(t)) {
                    el.click(); return t.slice(0, 60);
                }
            }
            return null;
        }""")
        if r:
            print(f"[click] entry (JS fallback): {r!r}")
            clicked = True
    if not clicked:
        print("!! no entry button found")
        browser.close()
        sys.exit(1)

    page.wait_for_timeout(4000)
    print(f"after entry click: {page.url[:120]}")

    # Step 2: If we're on a login/signup page, find and click Google button
    if "accounts.google.com" not in page.url:
        for sel in ["button:has-text('Continue with Google')",
                    "button:has-text('Sign in with Google')",
                    "a:has-text('Continue with Google')",
                    "button:has-text('Google')",
                    "[data-provider='google']",
                    "button:has-text('Google')"]:
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=4000):
                    loc.click(timeout=6000)
                    print(f"[click] Google button: {sel}")
                    break
            except Exception:
                continue
        page.wait_for_timeout(4000)
        print(f"after Google click: {page.url[:120]}")

    # Step 3: Handle Google flow across all pages (same-page nav or popup)
    deadline = time.time() + 90
    while time.time() < deadline:
        time.sleep(3)
        for pg in ctx.pages:
            if "accounts.google.com" in pg.url:
                handle_google(pg)
        # Check for strong auth cookie
        names = set()
        for c in ctx.cookies():
            dom = (c.get("domain") or "").lstrip(".").lower()
            if "perplexity.ai" in dom:
                names.add(c["name"])
        present = [n for n in STRONG if n in names]
        if present:
            print(f"\n[OK] SIGNED IN — strong cookies: {present}")
            browser.close()
            sys.exit(0)

    print("\ntimeout waiting for strong auth cookie")
    # Final cookie check
    names = set()
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".").lower()
        if "perplexity.ai" in dom:
            names.add(c["name"])
    print(f"final perplexity cookies: {sorted(names)}")
    browser.close()
