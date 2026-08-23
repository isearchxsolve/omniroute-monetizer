"""CDP Pilot & Recorder: Puter Google Account Select & Key Wire
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

def step_puter_complete():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    if not api.login():
        log("[-] OmniRoute login failed")
        return
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        
        # Find the accounts.google.com page or puter page
        google_page = None
        for p in ctx.pages:
            if "accounts.google.com" in p.url:
                google_page = p
                break
        
        if google_page:
            log("[1] Found Google Account Chooser tab. Bringing to front...")
            google_page.bring_to_front()
            
            # Click the account tile
            log("[2] Clicking Google account tile (isearch.xsolve@gmail.com)...")
            account_tile = google_page.locator("div:has-text('isearch.xsolve@gmail.com'), [data-identifier*='isearch.xsolve'], li:has-text('isearch.xsolve')").first
            if account_tile.count():
                account_tile.click()
            else:
                google_page.locator("div[role='link'], div[jsname]").first.click()
            
            log("    Clicked tile. Waiting for redirect...")
            time.sleep(5)
        
        # Now find the puter page
        puter_page = None
        for p in ctx.pages:
            if "puter.com" in p.url:
                puter_page = p
                break
        
        if not puter_page:
            puter_page = ctx.new_page()
            puter_page.goto("https://puter.com/app/developer", wait_until="domcontentloaded")
        
        puter_page.bring_to_front()
        log(f"[3] Active Puter page: {puter_page.url} | Title: {puter_page.title()}")
        time.sleep(3)
        puter_page.screenshot(path=str(SHOTS_DIR / "puter_logged_in_dashboard.png"))
        
        body = puter_page.inner_text("body")
        log("--- Puter Dashboard Body ---")
        log(body[:1500])
        
        # If not on developer app or API keys, navigate directly or click
        # Check for API Keys tab or Create button
        buttons = puter_page.locator("button, a, input").all()
        log(f"[4] Visible buttons ({len(buttons)} total):")
        for b in buttons:
            try:
                if b.is_visible():
                    t = (b.inner_text() or b.get_attribute("placeholder") or b.get_attribute("value") or "").strip()
                    if t:
                        log(f"    - [{b.evaluate('el => el.tagName')}] '{t}'")
            except Exception:
                pass
        
        # Look for existing API keys
        keys_found = re.findall(r"\b(sk-[A-Za-z0-9_\-]{20,}|puter_[A-Za-z0-9_\-]{20,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_\-]{32,})\b", body)
        # Filter noise
        clean_keys = [k for k in keys_found if not re.match(r"^(?:https?|webpack|sourcemap|csrf|nonce)", k, re.I)]
        
        if clean_keys:
            log(f"[+] Found {len(clean_keys)} candidate keys in body:")
            for k in clean_keys:
                log(f"    Key: {fingerprint(k)} (len={len(k)})")
            
            chosen_key = clean_keys[0]
            log(f"[*] Testing wiring for key: {fingerprint(chosen_key)} ...")
            res = wire(api, "puter", "puter", chosen_key)
            log(f"    Wire result: {res}")
        else:
            log("[-] No candidate keys found directly in body text. Inspecting copy buttons or create button...")
            copy_btns = puter_page.locator("button:has-text('Copy'), button:has-text('copy')").all()
            log(f"    Found {len(copy_btns)} Copy buttons.")
            if copy_btns:
                log("    Clicking first Copy button...")
                copy_btns[0].click()
                time.sleep(1)
                clip = puter_page.evaluate("navigator.clipboard.readText()")
                log(f"    Clipboard value: {fingerprint(clip) if clip else '(empty)'}")
                if clip:
                    res = wire(api, "puter", "puter", clip)
                    log(f"    Wire result: {res}")

if __name__ == "__main__":
    step_puter_complete()
