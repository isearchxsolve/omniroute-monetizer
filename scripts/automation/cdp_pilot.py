"""CDP Pilot & Recorder for OmniRoute Key Harvesting
Pilots individual providers step-by-step, captures DOM & screenshots, extracts keys, and records playbooks.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import re
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import wire, real_completion, fingerprint, KEYS_FILE, load_targets

SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

def pilot_featherless(pw, api):
    print("\n" + "="*70)
    print("[*] PILOTING: featherless-ai")
    print("="*70)
    
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    
    page = ctx.new_page()
    page.bring_to_front()
    
    # Step 1: Go to featherless.ai
    print("[1] Navigating to https://featherless.ai ...")
    page.goto("https://featherless.ai", wait_until="domcontentloaded", timeout=30000)
    time.sleep(2)
    page.screenshot(path=str(SHOTS_DIR / "featherless_1_landing.png"))
    print(f"    URL: {page.url} | Title: {page.title()}")
    
    # Check if bounced to Google Accounts or if we need to click Sign in / Account
    if "accounts.google.com" in page.url:
        print("[2] Auto-bounced to Google OAuth! Picking account...")
        # Handle Google Account chooser
        # Look for account tile
        tiles = page.locator("[data-identifier], [data-email], div[role='link'], li:has-text('@gmail.com')")
        print(f"    Account tiles count: {tiles.count()}")
        if tiles.count():
            tiles.first.click()
            print("    Clicked first Google account tile.")
            time.sleep(3)
        page.screenshot(path=str(SHOTS_DIR / "featherless_2_after_google.png"))
        print(f"    Landed URL: {page.url} | Title: {page.title()}")
    else:
        print("[2] On landing page. Checking for login / account buttons...")
        # Look for login/account buttons or direct navigation to /account/api-keys
        page.goto("https://featherless.ai/account/api-keys", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        page.screenshot(path=str(SHOTS_DIR / "featherless_2_apikeys_direct.png"))
        print(f"    Landed URL: {page.url} | Title: {page.title()}")
        if "accounts.google.com" in page.url:
            print("    Bounced to Google OAuth. Selecting account...")
            tiles = page.locator("[data-identifier], [data-email], div[role='link'], li:has-text('@gmail.com')")
            if tiles.count():
                tiles.first.click()
                print("    Clicked Google account tile.")
                time.sleep(4)
            page.screenshot(path=str(SHOTS_DIR / "featherless_3_after_google.png"))
            print(f"    URL after Google: {page.url} | Title: {page.title()}")

    # Step 3: Inspect the page DOM for keys or create key button
    print("[3] Inspecting /account/api-keys DOM...")
    page.screenshot(path=str(SHOTS_DIR / "featherless_4_dashboard.png"))
    body = page.inner_text("body")
    print(f"    Body snippet:\n{body[:600]}")
    
    # Check buttons and inputs
    buttons = page.locator("button, a[role='button']").all()
    print("    Visible buttons:")
    for b in buttons:
        try:
            if b.is_visible():
                print(f"      - '{b.inner_text().strip()}'")
        except Exception:
            pass

    # Look for "New API Key" / "Create" or existing key
    key_match = re.search(r"\b(hf_[A-Za-z0-9_\-]{16,}|sk-[A-Za-z0-9_\-]{16,}|[A-Za-z0-9_\-]{32,})\b", body)
    if key_match:
        print(f"[+] Found candidate key in page body: {key_match.group(0)[:8]}...")
    
    return page

if __name__ == "__main__":
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        pilot_featherless(pw, api)
