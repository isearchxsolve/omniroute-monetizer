"""Inspect the current HF /join page state via CDP.

Finds the existing /join tab (does NOT open a new one), reports:
- current URL
- whether an hCaptcha iframe / visible challenge is present
- any alert/error text
- takes a VIEWPORT screenshot (full-page times out on this machine)
"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0] if browser.contexts else None
    if not ctx:
        print("NO CONTEXT")
        raise SystemExit(0)

    # find existing /join page
    page = None
    for p in ctx.pages:
        if "/join" in p.url:
            page = p
            break
    if page is None:
        print("no /join tab found; pages:", [p.url for p in ctx.pages])
        page = ctx.new_page()
        page.goto("https://huggingface.co/join", timeout=60000, wait_until="domcontentloaded")

    page.bring_to_front()
    page.wait_for_timeout(1500)
    print("URL:", page.url)

    # hCaptcha detection
    hcaptcha_iframes = page.locator('iframe[src*="hcaptcha"]').count()
    print("hcaptcha iframes:", hcaptcha_iframes)
    # visible challenge box
    try:
        challenge_visible = page.locator('iframe[src*="hcaptcha"]').first.is_visible()
    except Exception:
        challenge_visible = False
    print("hcaptcha iframe visible:", challenge_visible)

    # is the submit button still there / enabled?
    try:
        btn = page.locator('button[type="submit"]:visible').last
        print("submit button text:", btn.inner_text(timeout=2000))
        print("submit enabled:", btn.is_enabled())
    except Exception as e:
        print("no submit button:", e)

    # alerts
    try:
        for el in page.locator('[role="alert"]').all()[:3]:
            t = (el.inner_text(timeout=1000) or "").strip()
            if t:
                print("ALERT:", t[:200])
    except Exception:
        pass

    body = ""
    try:
        body = page.locator("body").inner_text(timeout=3000)
    except Exception:
        pass
    low = body.lower()
    for marker in ["challenge-expired", "verify your email", "check your email",
                   "already", "exists", "in use", "error", "invalid"]:
        if marker in low:
            print("BODY MARKER:", marker)

    # viewport screenshot only (full-page times out here)
    try:
        page.screenshot(path=r"d:\omniroute-monetizer\evidence\hf_join_current.png", full_page=False, timeout=20000)
        print("screenshot: evidence/hf_join_current.png")
    except Exception as e:
        print("screenshot failed:", e)
