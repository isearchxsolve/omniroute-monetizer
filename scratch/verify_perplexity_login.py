"""Verify Perplexity login is REAL: check page state + strong cookie validity."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 9223
STRONG = ["__Secure-next-auth.session-token", "__Secure-perplexity_session"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    # Find perplexity page
    page = None
    for pg in ctx.pages:
        if "perplexity.ai" in pg.url:
            page = pg
            break

    if page:
        print(f"current URL: {page.url[:150]}")
        print(f"title: {page.title()!r}")
        # Try navigating to home to see if we're signed in
        page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)
        print(f"after home nav: {page.url[:150]}")

        # Check for sign-in vs signed-out indicators
        body_text = page.evaluate("() => document.body ? document.body.innerText.slice(0, 500) : ''")
        print(f"body preview: {body_text[:300]!r}")

    # Check cookies
    names = {}
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".").lower()
        if "perplexity.ai" in dom:
            names[c["name"]] = len(c.get("value") or "")

    print(f"\nperplexity cookies ({len(names)}):")
    for n in sorted(names):
        marker = " <-- STRONG" if n in STRONG else ""
        print(f"  {n} (len={names[n]}){marker}")

    present = [n for n in STRONG if n in names]
    if present:
        print(f"\n[OK] strong cookies present: {present}")
    else:
        print("\n[!!] NO strong cookies — login may be incomplete")

    browser.close()
