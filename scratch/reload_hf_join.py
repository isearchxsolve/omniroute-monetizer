"""Reload /join fresh and report state using CDP-native screenshot (bypasses Playwright font-wait hang)."""
import json, base64
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0] if browser.contexts else None
    if not ctx:
        print("NO CONTEXT"); raise SystemExit(0)

    # browser refuses new tabs on this overloaded machine — reuse an existing tab
    pages = ctx.pages
    print("open pages:", len(pages))
    for p in pages:
        print("  -", p.url[:80])
    page = None
    for p in pages:
        if "/join" in p.url:
            page = p; break
    if page is None:
        for p in pages:
            if p.url in ("about:blank", "chrome://newtab/", "chrome://new-tab-page/"):
                page = p; break
    if page is None and pages:
        page = pages[0]
    if page is None:
        print("NO PAGES AT ALL"); raise SystemExit(0)
    print("using page:", page.url[:80])
    page.goto("https://huggingface.co/join", timeout=60000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    page.bring_to_front()
    print("URL:", page.url)
    print("title:", page.title())

    print("email input count:", page.locator('input[name="email"]').count())
    print("password input count:", page.locator('input[name="password"]').count())
    print("hcaptcha iframes:", page.locator('iframe[src*="hcaptcha"]').count())

    # CDP-native screenshot (no font-wait)
    try:
        cdp = ctx.new_cdp_session(page)
        shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        data = base64.b64decode(shot["data"])
        with open(r"d:\omniroute-monetizer\evidence\hf_join_fresh.png", "wb") as f:
            f.write(data)
        print("CDP screenshot OK:", len(data), "bytes -> evidence/hf_join_fresh.png")
    except Exception as e:
        print("CDP screenshot failed:", e)

    body = ""
    try:
        body = page.locator("body").inner_text(timeout=3000)
    except Exception:
        pass
    print("body snippet:", body[:300].replace("\n", " | "))
