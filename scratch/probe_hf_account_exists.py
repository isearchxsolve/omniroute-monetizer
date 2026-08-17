"""Probe whether the HF account already exists by attempting step-1 of /join.

If the email is already registered, HF shows an "already" / "exists" error at step 1.
If step 2 (username) appears, the account does NOT exist yet.
Read-only w.r.t. account creation: we click Next but do NOT submit step 2.
"""
import json
import time
from playwright.sync_api import sync_playwright

with open(r"d:\omniroute-monetizer\state\hf_experiment_account.json") as f:
    acct = json.load(f)


def human_type(page, selector, text):
    el = page.locator(selector).first
    el.click()
    page.wait_for_timeout(200)
    page.keyboard.type(text, delay=45)


with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    try:
        page.goto("https://huggingface.co/join", timeout=60000, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        print("URL:", page.url)
        print("title:", page.title())

        # Is there even an email input? (maybe already logged in or different layout)
        if not page.locator('input[name="email"]').count():
            body = page.locator("body").inner_text(timeout=3000)[:500].replace("\n", " | ")
            print("NO email input. body:", body)
            raise SystemExit(0)

        human_type(page, 'input[name="email"]', acct["email"])
        if page.locator('input[name="password"]').count():
            human_type(page, 'input[name="password"]', acct["password"])
        page.wait_for_timeout(800)
        page.click('button[type="submit"]')
        print("step1 Next clicked")
        page.wait_for_timeout(3500)

        url = page.url
        print("post-submit URL:", url)

        # gather visible text + any alert/error elements
        alerts = []
        try:
            for el in page.locator('[role="alert"]').all()[:4]:
                t = (el.inner_text(timeout=1000) or "").strip()
                if t:
                    alerts.append(t[:200])
        except Exception:
            pass
        body = ""
        try:
            body = page.locator("body").inner_text(timeout=3000)
        except Exception:
            pass
        low = body.lower()

        print("ALERTS:", alerts)

        has_username = page.locator('input[name="username"]').count() > 0
        print("step2 username field visible:", has_username)

        verdict = "UNKNOWN"
        if has_username:
            verdict = "ACCOUNT_DOES_NOT_EXIST (step2 shown -> safe to complete signup)"
        elif any(k in low for k in ["already", "exists", "in use", "taken", "registered"]):
            verdict = "ACCOUNT_EXISTS (email already registered -> need resend-verification)"
        elif "verify" in low or "check your email" in low:
            verdict = "ACCOUNT_EXISTS_PENDING_VERIFY"
        print("VERDICT:", verdict)
        print("body snippet:", body[:600].replace("\n", " | "))
        page.screenshot(path=r"d:\omniroute-monetizer\evidence\hf_probe_step1.png", full_page=True)
        print("screenshot: evidence/hf_probe_step1.png")
    finally:
        page.close()
