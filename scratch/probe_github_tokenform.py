#!/usr/bin/env python3
"""Probe GitHub classic-token creation form (read-only, no submit).
Navigates Generate new token -> classic -> dumps form fields + detects sudo wall."""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")
OUT = os.path.join(ROOT, "state", "dom_recon")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()
    page.goto("https://github.com/settings/tokens", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    page.get_by_role("button", name="Generate new token").first.click(timeout=8000)
    page.wait_for_timeout(1500)
    # menu: choose classic
    try:
        page.get_by_role("menuitem", name="Generate new token (classic)").first.click(timeout=5000)
    except Exception:
        try:
            page.get_by_text("Generate new token (classic)").first.click(timeout=5000)
        except Exception as e:
            print("classic menuitem click failed:", e)
    page.wait_for_timeout(3000)
    print("URL:", page.url)
    print("TITLE:", page.title())
    body = page.evaluate("() => document.body.innerText.slice(0, 1500)")
    print("BODY SAMPLE:")
    print(body[:1200])
    # detect sudo wall
    if "password" in page.url.lower() or "sudo" in page.url.lower() or "Confirm access" in body:
        print("\n[!] SUDO/PASSWORD WALL DETECTED at", page.url)
    # dump inputs
    print("\n--- inputs ---")
    for i in page.locator("input, textarea, select").all()[:30]:
        try:
            if not i.is_visible():
                continue
            print(f"  tag={i.evaluate('el=>el.tagName')} type={i.get_attribute('type')} name={i.get_attribute('name')} id={i.get_attribute('id')} ph={i.get_attribute('placeholder')}")
        except Exception:
            pass
    with open(os.path.join(OUT, "github_tokenform.json"), "w", encoding="utf-8") as f:
        json.dump({"url": page.url, "title": page.title(), "body": body}, f, indent=2, ensure_ascii=False)
    browser.close()
print("\ndone")
