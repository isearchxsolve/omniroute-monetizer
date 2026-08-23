"""Click API Keys on platform.reka.ai and extract/create key.
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

def step2_reka():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        print("[1] Opening platform.reka.ai ...")
        page.goto("https://platform.reka.ai", wait_until="domcontentloaded", timeout=25000)
        time.sleep(3)
        print(f"    Landed URL: {page.url} | Title: {page.title()}")
        
        # Click "API Keys"
        print("[2] Clicking 'API Keys' sidebar control...")
        key_link = page.locator("a:has-text('API Keys'), button:has-text('API Keys')").first
        if key_link.count():
            key_link.click()
            time.sleep(3)
            print(f"    Current URL after click: {page.url} | Title: {page.title()}")
            page.screenshot(path=str(SHOTS_DIR / "reka_api_keys_view.png"))
            
            body = page.inner_text("body")
            print("--- Body Content ---")
            print(body[:1200])
            
            # Check for create button
            create_btn = page.locator("button:has-text('Create'), button:has-text('New API Key'), button:has-text('Generate')").first
            if create_btn.count() and create_btn.is_visible():
                print(f"[+] Found create button: '{create_btn.inner_text()}'. Clicking...")
                create_btn.click()
                time.sleep(2)
                
                # Check for modal name input
                modal_input = page.locator("input[placeholder*='name' i], input[type=text]").first
                if modal_input.count() and modal_input.is_visible():
                    modal_input.fill(f"omniroute-auto-{int(time.time())}")
                    modal_submit = page.locator("button:has-text('Create'), button:has-text('Generate'), button:has-text('Save')").first
                    if modal_submit.count():
                        modal_submit.click()
                        time.sleep(2)
                
                # Re-read body
                body = page.inner_text("body")
                print("--- Post Create Body ---")
                print(body[:1200])
            
            # Look for keys in body or inputs
            key_match = re.findall(r"\b(sk-[A-Za-z0-9_\-]{20,}|reka_[A-Za-z0-9_\-]{20,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_\-]{32,})\b", body)
            clean_keys = [k for k in key_match if not re.match(r"^(?:https?|webpack|sourcemap|csrf|nonce|omniroute)", k, re.I)]
            if clean_keys:
                print(f"[+] Found key candidates: {[fingerprint(k) for k in clean_keys]}")
                # Wire into OmniRoute
                chosen = clean_keys[0]
                print(f"[*] Wiring Reka key into OmniRoute: {fingerprint(chosen)} ...")
                res = wire(api, "reka", "reka", chosen)
                print(f"    Wire result: {res}")
            else:
                # Try copy buttons
                copy_btns = page.locator("button:has-text('Copy'), [aria-label*='copy' i]").all()
                print(f"    Copy buttons count: {len(copy_btns)}")
                if copy_btns:
                    copy_btns[0].click()
                    time.sleep(1)
                    clip = page.evaluate("navigator.clipboard.readText()")
                    print(f"    Clipboard: {fingerprint(clip) if clip else '(empty)'}")
                    if clip:
                        res = wire(api, "reka", "reka", clip)
                        print(f"    Wire result: {res}")

if __name__ == "__main__":
    step2_reka()
