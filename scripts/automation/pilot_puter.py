"""CDP Pilot & Recorder: Puter Key Harvesting & Testing
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

def log(msg):
    print(msg, flush=True)

def pilot_puter(pw, api):
    log("\n" + "="*70)
    log("[*] PILOTING: puter")
    log("="*70)
    
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    
    page = ctx.new_page()
    page.bring_to_front()
    
    # Step 1: Puter entry points: https://puter.com, https://developer.puter.com, or https://puter.com/account/api-keys
    target_urls = ["https://developer.puter.com", "https://puter.com", "https://puter.com/app/developer"]
    
    for url in target_urls:
        log(f"[1] Navigating to {url} ...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(2)
            log(f"    Landed URL: {page.url} | Title: {page.title()}")
            page.screenshot(path=str(SHOTS_DIR / f"puter_{url.split('//')[-1].replace('/', '_')}.png"))
            
            body = page.inner_text("body")
            log(f"    Body snippet: {body[:300].replace(chr(10), ' ')}")
            
            # Check for sign-in or account buttons
            buttons = page.locator("button, a").all()
            log(f"    Found {len(buttons)} controls on page")
            
            # Look for API keys / token patterns
            key_match = re.findall(r"\b(sk-[A-Za-z0-9_\-]{20,}|puter_[A-Za-z0-9_\-]{20,}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[A-Za-z0-9_\-]{32,})\b", body)
            if key_match:
                log(f"    Potential keys found: {len(key_match)}")
                for k in key_match[:3]:
                    log(f"      Candidate: {fingerprint(k)}")
            
            # Look for copy buttons or API keys menu
            for b in buttons:
                try:
                    t = b.inner_text().strip()
                    if re.search(r"api key|token|developer|dashboard|sign in|log in|google", t, re.I):
                        log(f"    Interesting control: '{t}' (tag={b.evaluate('el => el.tagName')})")
                except Exception:
                    pass
        except Exception as e:
            log(f"    [-] Navigation error for {url}: {e}")

if __name__ == "__main__":
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        pilot_puter(pw, api)
