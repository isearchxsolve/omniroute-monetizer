"""CDP Pilot & Recorder: Puter Google Login & Key Capture
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

def log(msg):
    print(msg, flush=True)

def step_puter_login_and_key():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        log(f"[1] Going to https://puter.com/app/developer ...")
        page.goto("https://puter.com/app/developer", wait_until="domcontentloaded", timeout=25000)
        time.sleep(2)
        
        # Click "Sign in with Google" button
        log("[2] Looking for 'Sign in with Google' button...")
        google_btn = page.locator("button:has-text('Sign in with Google'), button:has-text('Log in with Google')").first
        if google_btn.count() and google_btn.is_visible():
            log("    Clicking 'Sign in with Google'...")
            # Note: could open popup or redirect
            with ctx.expect_page(timeout=10000) as new_page_info:
                google_btn.click()
            
            popup = new_page_info.value
            log(f"[3] Popup opened: {popup.url} | Title: {popup.title()}")
            popup.bring_to_front()
            time.sleep(2)
            popup.screenshot(path=str(SHOTS_DIR / "puter_google_popup.png"))
            
            # If on Google account chooser, select account
            if "accounts.google.com" in popup.url:
                log("    Handling Google Account chooser...")
                tiles = popup.locator("[data-identifier], [data-email], div[role='link'], li:has-text('@gmail.com')")
                if tiles.count():
                    log(f"    Found {tiles.count()} Google account tiles. Clicking first...")
                    tiles.first.click()
                    time.sleep(5)
                else:
                    log("    No account tiles found directly. Looking for generic clickables...")
                    popup.locator("div[jsname], div[role='button']").first.click()
                    time.sleep(5)
        
        # Settle on main page
        time.sleep(4)
        page.bring_to_front()
        log(f"[4] Main page URL: {page.url} | Title: {page.title()}")
        page.screenshot(path=str(SHOTS_DIR / "puter_after_login.png"))
        
        body = page.inner_text("body")
        log("--- Main Page Body Snippet ---")
        log(body[:1200])
        
        # Check for API keys, Copy buttons, or create key buttons
        buttons = page.locator("button, a, input").all()
        log(f"[5] Found {len(buttons)} controls on developer dashboard:")
        for b in buttons:
            try:
                if b.is_visible():
                    t = (b.inner_text() or b.get_attribute("placeholder") or b.get_attribute("value") or "").strip()
                    if t:
                        log(f"    - [{b.evaluate('el => el.tagName')}] '{t}'")
            except Exception:
                pass

        # Check for keys in DOM
        keys_found = re.findall(r"\b(sk-[A-Za-z0-9_\-]{20,}|puter_[A-Za-z0-9_\-]{20,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_\-]{32,})\b", body)
        if keys_found:
            log(f"[+] Found {len(keys_found)} key candidates:")
            for k in keys_found:
                log(f"    Candidate: {fingerprint(k)} (len={len(k)})")

if __name__ == "__main__":
    step_puter_login_and_key()
