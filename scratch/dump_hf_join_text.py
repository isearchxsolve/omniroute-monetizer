"""Read-only: dump the live /join page state as text (no vision available)."""
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0] if browser.contexts else None
    if not ctx:
        print("NO CONTEXT"); raise SystemExit(0)

    page = None
    for p in ctx.pages:
        if "/join" in p.url:
            page = p; break
    if page is None:
        print("no /join tab; pages:", [p.url for p in ctx.pages]); raise SystemExit(0)

    print("URL:", page.url)

    # form field state
    for name in ["email", "password", "username", "fullname"]:
        try:
            loc = page.locator(f'input[name="{name}"]')
            if loc.count():
                v = loc.first.input_value(timeout=2000)
                print(f"  input[{name}]: present, value_len={len(v)}, filled={bool(v)}")
        except Exception as e:
            print(f"  input[{name}]: error {e}")

    # submit button
    try:
        btns = page.locator('button[type="submit"]:visible')
        print("visible submit buttons:", btns.count())
        for i in range(min(btns.count(), 3)):
            print(f"  btn{i}: '{btns.nth(i).inner_text(timeout=1500)}' enabled={btns.nth(i).is_enabled()}")
    except Exception as e:
        print("submit btn error:", e)

    # alerts / error text
    try:
        for el in page.locator('[role="alert"]').all()[:4]:
            t = (el.inner_text(timeout=1000) or "").strip()
            if t:
                print("ALERT:", t[:200])
    except Exception:
        pass

    # all iframes on page
    try:
        iframes = page.locator("iframe")
        n = iframes.count()
        print("total iframes:", n)
        for i in range(min(n, 10)):
            src = iframes.nth(i).get_attribute("src") or ""
            print(f"  iframe{i}: {src[:120]}")
    except Exception as e:
        print("iframe scan error:", e)

    # body text
    try:
        body = page.locator("body").inner_text(timeout=4000)
        print("BODY (800):", body[:800].replace("\n", " | "))
    except Exception as e:
        print("body error:", e)
