"""Click Google account chooser and follow to Puter developer dashboard.
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

def log(msg):
    print(msg, flush=True)

def run():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        
        # Find Google chooser tab
        google_page = None
        for p in ctx.pages:
            if "accounts.google.com" in p.url:
                google_page = p
                break
        
        if not google_page:
            log("No Google accounts tab found. Pages open:")
            for p in ctx.pages:
                log(f"  {p.url}")
            return
        
        google_page.bring_to_front()
        log(f"[1] On Google tab: {google_page.url}")
        
        # Inspect clickables
        tiles = google_page.locator("div[data-identifier], li[data-identifier], div[role='link'], [data-email]")
        log(f"    Tiles found: {tiles.count()}")
        for i in range(tiles.count()):
            try:
                t = tiles.nth(i)
                log(f"    Tile {i}: data-identifier='{t.get_attribute('data-identifier')}' text='{t.inner_text().replace(chr(10), ' ')}'")
            except Exception:
                pass
        
        # Click the tile
        target_tile = google_page.locator("[data-identifier*='isearch.xsolve'], li[data-identifier], div[role='link']").first
        log("[2] Clicking account tile...")
        target_tile.click()
        
        # Wait up to 15s for redirect to finish
        end = time.monotonic() + 15
        while time.monotonic() < end:
            time.sleep(1)
            urls = [p.url for p in ctx.pages]
            log(f"    Current URLs: {urls}")
            if any("puter.com" in u and "accounts.google.com" not in u for u in urls):
                log("[+] Redirect to puter completed!")
                break
        
        time.sleep(3)
        # Find puter page
        for p in ctx.pages:
            if "puter.com" in p.url:
                p.bring_to_front()
                log(f"[3] Landed Puter page: {p.url} | Title: {p.title()}")
                p.screenshot(path=str(SHOTS_DIR / "puter_landing_after_auth.png"))
                body = p.inner_text("body")
                log(f"    Body snippet:\n{body[:800]}")
                break

if __name__ == "__main__":
    run()
