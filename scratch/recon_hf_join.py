"""Recon: inspect huggingface.co/join form structure via CDP Chrome."""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://huggingface.co/join", timeout=45000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        print("URL:", page.url)
        print("Title:", page.title())

        # captcha detectors
        checks = {
            "turnstile_iframe": page.locator("iframe[src*='challenges.cloudflare.com']").count(),
            "turnstile_div": page.locator("[class*='turnstile'], #challenge-stage, .cf-turnstile").count(),
            "recaptcha": page.locator(".g-recaptcha, iframe[src*='recaptcha']").count(),
            "hcaptcha": page.locator(".h-captcha, iframe[src*='hcaptcha']").count(),
        }
        print("CAPTCHA CHECKS:", json.dumps(checks))

        inputs = page.eval_on_selector_all(
            "input,button[type='submit'],button",
            """els => els.slice(0, 40).map(e => ({
                tag: e.tagName,
                type: e.type || '',
                name: e.name || '',
                id: e.id || '',
                placeholder: e.placeholder || '',
                autocomplete: e.getAttribute('autocomplete') || '',
                text: (e.innerText || '').trim().slice(0, 60),
                visible: !!(e.offsetWidth || e.offsetHeight),
            }))"""
        )
        for i in inputs:
            print(json.dumps(i))

        page.screenshot(path=r"d:\omniroute-monetizer\evidence\hf_join_recon.png", full_page=True)
        print("screenshot saved")
    finally:
        page.close()
