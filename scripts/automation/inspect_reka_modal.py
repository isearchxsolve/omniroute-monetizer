"""Inspect Reka modal DOM structure.
"""
from __future__ import annotations
import sys
import json
import time
import pathlib
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT

SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def inspect_reka_modal():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        print("[+] URL:", page.url)
        page.screenshot(path=str(SHOTS_DIR / "reka_modal_inspect.png"))
        
        # Check inputs and buttons in modal
        inputs = page.locator("input").all()
        print(f"[+] Total inputs on page: {len(inputs)}")
        for idx, inp in enumerate(inputs):
            try:
                print(f"  Input {idx}: type={inp.get_attribute('type')} placeholder='{inp.get_attribute('placeholder')}' val='{inp.input_value()}' vis={inp.is_visible()}")
            except Exception as e:
                print(f"  Input {idx} error: {e}")
                
        buttons = page.locator("button").all()
        print(f"[+] Total buttons on page: {len(buttons)}")
        for idx, btn in enumerate(buttons):
            try:
                print(f"  Button {idx}: text='{btn.inner_text()}' vis={btn.is_visible()} aria-label='{btn.get_attribute('aria-label')}'")
            except Exception as e:
                print(f"  Button {idx} error: {e}")

if __name__ == "__main__":
    inspect_reka_modal()
