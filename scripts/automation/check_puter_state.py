"""Check puter.com session and cookies
"""
from __future__ import annotations
import pathlib
import sys
import time
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT

SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def check():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        print(f"[+] Going to https://puter.com ...")
        page.goto("https://puter.com", wait_until="domcontentloaded")
        time.sleep(3)
        page.screenshot(path=str(SHOTS_DIR / "puter_main_desktop.png"))
        print(f"URL: {page.url} | Title: {page.title()}")
        body = page.inner_text("body")
        print("Body text:")
        print(body[:800].replace(chr(10), " "))
        
        # Check cookies on puter.com
        cookies = ctx.cookies(["https://puter.com"])
        print(f"[+] Puter cookies count: {len(cookies)}")
        for c in cookies:
            print(f"    Cookie: {c['name']} (domain={c['domain']})")

if __name__ == "__main__":
    check()
