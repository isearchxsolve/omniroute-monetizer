"""Interact with Reka create modal and existing keys.
"""
from __future__ import annotations
import sys
import json
import time
import re
import pathlib
import subprocess
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import wire, real_completion, fingerprint, save_key

sys.stdout.reconfigure(encoding="utf-8")
SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def run_reka():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        # 1. First test: Click Button 5 (the icon beside the existing key)
        print("[1] Clicking Button 5 (icon beside existing key)...")
        buttons = page.locator("button").all()
        if len(buttons) > 5:
            buttons[5].click()
            time.sleep(1)
            # Read clipboard via powershell
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True)
            clip = (out.stdout or "").strip()
            print(f"    Clipboard read after Button 5 click: {fingerprint(clip) if clip else '(empty)'}")
            if clip and len(clip) >= 20 and not " " in clip:
                print(f"[+] SUCCESS! Got key from Button 5: {fingerprint(clip)}")
                print("[*] Wiring key to OmniRoute...")
                res = wire(api, "reka", "Reka", clip)
                print(f"    Wire result: {res}")
                if res.get("ok"):
                    save_key("reka", clip, True, res.get("detail", ""))
                    print("[+] SAVED TO KEYS_FILE!")
                return
                
        # 2. Fill the modal name input and click "Create new key"
        print("[2] Filling input and clicking 'Create new key'...")
        inp = page.locator("input").first
        if inp.count() and inp.is_visible():
            inp.fill("omniroute-auto-pilot")
            time.sleep(1)
            create_btn = page.locator("button:has-text('Create new key')").first
            if create_btn.count():
                create_btn.click()
                time.sleep(3)
                page.screenshot(path=str(SHOTS_DIR / "reka_modal_post_create.png"))
                
                # Check clipboard
                out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True)
                clip = (out.stdout or "").strip()
                print(f"    Clipboard read: {fingerprint(clip) if clip else '(empty)'}")
                
                # Check body and new inputs
                body = page.inner_text("body")
                print("--- Body ---")
                print(body[:800])
                
                # Check if new inputs or copy buttons appeared
                inputs = page.locator("input, code, pre").all()
                for i in inputs:
                    try:
                        v = (i.input_value() if i.evaluate("el => el.tagName") == "INPUT" else i.inner_text()).strip()
                        if len(v) >= 24 and not " " in v and not re.match(r"^(?:omniroute|http)", v):
                            print(f"[+] Found candidate key: {fingerprint(v)}")
                            res = wire(api, "reka", "Reka", v)
                            print(f"    Wire result: {res}")
                            if res.get("ok"):
                                save_key("reka", v, True, res.get("detail", ""))
                                print("[+] SAVED TO KEYS_FILE!")
                            return
                    except Exception:
                        pass

if __name__ == "__main__":
    run_reka()
