"""Read-only: screenshot the live /join tab via CDP to see the current hCaptcha state."""
import base64
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
    print("hcaptcha iframes:", page.locator('iframe[src*="hcaptcha"]').count())
    try:
        vis = page.locator('iframe[src*="hcaptcha"]').first.is_visible()
    except Exception:
        vis = False
    print("hcaptcha iframe visible:", vis)

    # look for the challenge container / checkbox
    for sel in ['iframe[title*="hCaptcha"]', '.hcaptcha', '[data-sitekey]',
                'iframe[src*="challenge"]', 'iframe[src*="newassets.hcaptcha"]']:
        try:
            c = page.locator(sel).count()
            if c:
                print(f"  {sel}: {c}")
        except Exception:
            pass

    try:
        cdp = ctx.new_cdp_session(page)
        shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        with open(r"d:\omniroute-monetizer\evidence\hf_captcha_now.png", "wb") as f:
            f.write(base64.b64decode(shot["data"]))
        print("screenshot -> evidence/hf_captcha_now.png")
    except Exception as e:
        print("screenshot failed:", e)
