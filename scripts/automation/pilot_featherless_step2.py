"""CDP Pilot & Recorder: Featherless API Key creation click & test
"""
from __future__ import annotations
import pathlib
import sys
import time
import json
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import wire, real_completion, fingerprint, KEYS_FILE, load_targets

SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def step_featherless_create():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        print(f"[+] Active Page URL: {page.url}")
        if "api-keys" not in page.url:
            page.goto("https://featherless.ai/account/api-keys", wait_until="domcontentloaded")
            time.sleep(2)
        
        # Click "New API Key" button
        btn = page.get_by_role("button", name="New API Key").first
        if btn.count() and btn.is_visible():
            print("[+] Clicking 'New API Key' button...")
            btn.click()
            time.sleep(2)
            page.screenshot(path=str(SHOTS_DIR / "featherless_5_after_click_new.png"))
            
            # Inspect dialog or body text
            body = page.inner_text("body")
            print("--- Post-Click Body Snippet ---")
            print(body[:800])
            
            # Check for inputs (name field or credit card field)
            inputs = page.locator("input").all()
            print(f"[+] Found {len(inputs)} inputs:")
            for inp in inputs:
                try:
                    if inp.is_visible():
                        print(f"    - type={inp.get_attribute('type')} name={inp.get_attribute('name')} placeholder={inp.get_attribute('placeholder')}")
                except Exception:
                    pass

if __name__ == "__main__":
    step_featherless_create()
