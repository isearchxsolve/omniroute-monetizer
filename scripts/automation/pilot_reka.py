"""Pilot Reka and Typhoon via CDP Playbook.
"""
from __future__ import annotations
import sys
import json
import time
import re
import pathlib
import requests
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import wire, real_completion, fingerprint, KEYS_FILE

sys.stdout.reconfigure(encoding="utf-8")
SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def pilot_reka():
    print("\n" + "="*70)
    print("[*] PILOTING: reka")
    print("="*70)
    
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.bring_to_front()
        
        # Reka entry points: https://chat.reka.ai, https://platform.reka.ai, or https://reka.ai
        print("[1] Navigating to https://chat.reka.ai ...")
        try:
            page.goto("https://chat.reka.ai", wait_until="domcontentloaded", timeout=25000)
            time.sleep(3)
            print(f"    URL: {page.url} | Title: {page.title()}")
            page.screenshot(path=str(SHOTS_DIR / "reka_1_landing.png"))
            
            body = page.inner_text("body")
            print(f"    Body snippet: {body[:300].replace(chr(10), ' ')}")
            
            # Check for Google login
            google_btn = page.locator("button:has-text('Google'), a:has-text('Google'), [aria-label*='Google' i]").first
            if google_btn.count() and google_btn.is_visible():
                print("[2] Found Google button. Clicking...")
                google_btn.click()
                time.sleep(3)
                
                # Check for Google account chooser
                if "accounts.google.com" in page.url or any("accounts.google.com" in p.url for p in ctx.pages):
                    gp = [p for p in ctx.pages if "accounts.google.com" in p.url][0]
                    gp.bring_to_front()
                    tile = gp.locator("[data-identifier*='isearch.xsolve'], li[data-identifier], div[role='link']").first
                    if tile.count():
                        print("    Clicking Google account tile on Reka...")
                        tile.click()
                        time.sleep(5)
                        
            # After login, check current page
            page.bring_to_front()
            print(f"[3] Current Page: {page.url} | Title: {page.title()}")
            page.screenshot(path=str(SHOTS_DIR / "reka_2_dashboard.png"))
            
            # Check if there is an API keys / developer settings link
            page.goto("https://platform.reka.ai/api-keys", wait_until="domcontentloaded", timeout=25000)
            time.sleep(3)
            print(f"[4] API Keys URL: {page.url} | Title: {page.title()}")
            page.screenshot(path=str(SHOTS_DIR / "reka_3_keys.png"))
            
            body_keys = page.inner_text("body")
            print("--- Reka Keys Body ---")
            print(body_keys[:800])
            
            buttons = page.locator("button, a").all()
            print(f"    Buttons ({len(buttons)}):")
            for b in buttons:
                try:
                    if b.is_visible():
                        t = b.inner_text().strip()
                        if t:
                            print(f"      - {t}")
                except Exception:
                    pass
        except Exception as exc:
            print(f"[-] Reka error: {exc}")

if __name__ == "__main__":
    pilot_reka()
