"""Shallow check: is Chrome CDP 9222 alive and logged into HuggingFace?"""
import json
import urllib.request

try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=5) as r:
        print("CDP alive:", json.loads(r.read().decode()).get("Browser"))
except Exception as e:
    print("CDP NOT reachable:", e)
    raise SystemExit(0)

from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0] if browser.contexts else None
    print("contexts:", len(browser.contexts))
    page = ctx.new_page() if ctx else None
    try:
        page.goto("https://huggingface.co/settings/tokens", timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        url = page.url
        title = page.title()
        print("final URL:", url)
        print("title:", title)
        if "/login" in url or "/join" in url:
            print("HF SESSION: NOT LOGGED IN (redirected to auth)")
        else:
            print("HF SESSION: LOGGED IN")
            body = page.locator("body").inner_text()[:800]
            print("body snippet:", body.replace("\n", " | ")[:600])
    finally:
        page.close()
