#!/usr/bin/env python3
"""Re-capture Anthropic dialog after filling name, to see why Add is disabled
and the exact expiration control. Read-only (no submit)."""
import json, os, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")
OUT = os.path.join(ROOT, "state", "dom_recon")
KEY_NAME = "omniroute-monetizer-probe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1360, "height": 950})
    page = ctx.new_page()
    page.goto("https://platform.claude.com/settings/keys", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    page.get_by_role("button", name="Create key").first.click(timeout=8000)
    page.wait_for_timeout(2000)
    dlg = page.locator('[role="dialog"]').first
    print("DIALOG TEXT:")
    print(dlg.inner_text()[:600])
    print("\n--- filling name ---")
    dlg.locator('input[placeholder="my-secret-key"]').first.fill(KEY_NAME)
    page.wait_for_timeout(800)
    add = dlg.locator('button[type="submit"]').first
    print("Add disabled after name fill?", add.is_disabled())
    print("\n--- all buttons in dialog ---")
    for b in dlg.locator("button").all():
        try:
            print(f"  text={b.inner_text()!r} type={b.get_attribute('type')} disabled={b.is_disabled()} aria={b.get_attribute('aria-label')}")
        except Exception as e:
            print("  (err)", e)
    print("\n--- all inputs in dialog ---")
    for i in dlg.locator("input, textarea, select").all():
        try:
            print(f"  tag={i.evaluate('el=>el.tagName')} type={i.get_attribute('type')} ph={i.get_attribute('placeholder')} value={i.input_value() if i.get_attribute('type')!='hidden' else '?'}")
        except Exception as e:
            print("  (err)", e)
    # dump dialog html for structure
    with open(os.path.join(OUT, "anthropic_dialog_probe.html"), "w", encoding="utf-8") as f:
        f.write(dlg.inner_html())
    print("\nhtml ->", os.path.join(OUT, "anthropic_dialog_probe.html"))
    browser.close()
