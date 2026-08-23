"""Click Continue on Google Consent Screen and Land on Puter Dashboard.
"""
from __future__ import annotations
import pathlib
import sys
import time
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

def run():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        
        # Find Google consent tab
        google_page = None
        for p in ctx.pages:
            if "accounts.google.com" in p.url:
                google_page = p
                break
        
        if google_page:
            google_page.bring_to_front()
            log(f"[1] On Google Consent Page: {google_page.url}")
            
            # Click "Continue" button
            continue_btn = google_page.locator("button:has-text('Continue'), div[role='button']:has-text('Continue')").first
            log(f"    Found Continue button: count={continue_btn.count()}")
            if continue_btn.count():
                log("[2] Clicking 'Continue' button...")
                continue_btn.click()
                time.sleep(6)
        
        # Now find puter page
        log("[3] Looking for Puter page...")
        puter_page = None
        for p in ctx.pages:
            if "puter.com" in p.url:
                puter_page = p
                break
        
        if puter_page:
            puter_page.bring_to_front()
            log(f"[4] Landed on Puter Page: {puter_page.url} | Title: {puter_page.title()}")
            time.sleep(3)
            puter_page.screenshot(path=str(SHOTS_DIR / "puter_consent_landed.png"))
            
            body = puter_page.inner_text("body")
            log("--- Puter Page Body ---")
            log(body[:1500])
            
            # Check for API keys
            buttons = puter_page.locator("button, a").all()
            log(f"[5] Found {len(buttons)} controls:")
            for b in buttons:
                try:
                    if b.is_visible():
                        t = b.inner_text().strip()
                        if t:
                            log(f"    - [{b.evaluate('el => el.tagName')}] '{t}'")
                except Exception:
                    pass

if __name__ == "__main__":
    run()
