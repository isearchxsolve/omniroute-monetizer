"""Create new key in Reka modal and wire to OmniRoute.
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
from harvest_free_keys import wire, real_completion, fingerprint, KEYS_FILE, save_key

sys.stdout.reconfigure(encoding="utf-8")
SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def step3_reka():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.bring_to_front()
        
        print("[1] On Reka page. Filling key name...")
        key_name = f"omniroute-auto-{int(time.time())}"
        name_input = page.locator("input[placeholder*='name' i], input[type=text]").first
        if name_input.count():
            name_input.fill(key_name)
            time.sleep(1)
            
        print("[2] Clicking 'Create new key' submit button...")
        submit_btn = page.locator("button:has-text('Create new key')").first
        if submit_btn.count():
            submit_btn.click()
            time.sleep(3)
            
        page.screenshot(path=str(SHOTS_DIR / "reka_after_submit_key.png"))
        body = page.inner_text("body")
        print("--- Post Submit Body ---")
        print(body[:1200])
        
        # Check modal inputs or pre/code tags or clipboard
        inputs = page.locator("input, code, pre").all()
        extracted_key = None
        for inp in inputs:
            try:
                val = inp.input_value() if inp.evaluate("el => el.tagName") == "INPUT" else inp.inner_text()
                val = val.strip()
                if len(val) >= 24 and not " " in val and not re.match(r"^(?:omniroute|http)", val):
                    print(f"[+] Found candidate in input/code: {fingerprint(val)}")
                    extracted_key = val
                    break
            except Exception:
                pass
                
        # Try copy button
        copy_btn = page.locator("button:has-text('Copy'), button:has([aria-label*='copy' i]), svg").first
        if not extracted_key:
            copy_btn = page.locator("button:has-text('Copy')").first
            if copy_btn.count():
                print("[+] Clicking modal Copy button...")
                copy_btn.click()
                time.sleep(1)
                clip = page.evaluate("navigator.clipboard.readText()")
                if clip and len(clip) >= 20:
                    print(f"[+] Clipboard read: {fingerprint(clip)}")
                    extracted_key = clip
                    
        # If still not found, search regex in body
        if not extracted_key:
            m = re.findall(r"\b([A-Za-z0-9_\-]{30,})\b", body)
            for cand in m:
                if not re.match(r"^(?:omniroute|http|webpack|sourcemap)", cand, re.I):
                    extracted_key = cand
                    break
                    
        if extracted_key:
            print(f"[+] SUCCESS! Extracted Reka key: {fingerprint(extracted_key)} (len={len(extracted_key)})")
            print(f"[*] Wiring Reka key into OmniRoute...")
            res = wire(api, "reka", "Reka", extracted_key)
            print(f"    Wire result: {res}")
            if res.get("ok"):
                save_key("reka", extracted_key, True, res.get("detail", ""))
                print("[+] SAVED REKA KEY TO KEYS_FILE!")
        else:
            print("[-] Could not extract key from modal.")

if __name__ == "__main__":
    step3_reka()
