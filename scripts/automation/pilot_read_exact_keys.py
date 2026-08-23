"""Read exact plaintext keys from active browser tabs for OpenAdapter and Reka.
"""
from __future__ import annotations
import sys
import json
import time
import re
import pathlib
import requests
import subprocess
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT
from oauth_keepalive import resolve_password
from omniroute_api import OmniRouteAPI
from harvest_free_keys import wire, fingerprint, save_key, KEYS_FILE

sys.stdout.reconfigure(encoding="utf-8")

def read_and_wire_both():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    api = OmniRouteAPI(password=resolve_password())
    api.login()
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        
        # 1. READ OPENADAPTER
        oa_page = ctx.new_page()
        oa_page.bring_to_front()
        print("[1] Navigating to OpenAdapter keys page...")
        oa_page.goto("https://dashboard.openadapter.in/keys", wait_until="domcontentloaded")
        time.sleep(2)
        show_btn = oa_page.locator("button:has-text('show'), button:has-text('Show')").first
        if show_btn.count():
            show_btn.click()
            time.sleep(1)
        
        # Read key from body
        body = oa_page.inner_text("body")
        oa_key = None
        for m in re.finditer(r"\b(sk-[A-Za-z0-9_\-]{20,})\b", body):
            candidate = m.group(1).strip()
            print(f"    Testing OpenAdapter candidate: {fingerprint(candidate)}")
            r = requests.get("https://api.openadapter.in/v1/models", headers={"Authorization": f"Bearer {candidate}"}, timeout=8)
            if r.status_code == 200:
                print(f"[+] VERIFIED OpenAdapter key: {fingerprint(candidate)} (len={len(candidate)})")
                oa_key = candidate
                break
                
        if oa_key:
            save_key("openadapter", oa_key, True, "Verified upstream models 200 OK")
            # Wire into OmniRoute
            w = wire(api, "openadapter", "OpenAdapter", oa_key)
            print(f"    OmniRoute wire result: {w}")
        oa_page.close()
        
        # 2. READ REKA
        reka_page = ctx.new_page()
        reka_page.bring_to_front()
        print("\n[2] Navigating to Reka API keys page...")
        reka_page.goto("https://platform.reka.ai/apikeys", wait_until="domcontentloaded")
        time.sleep(2)
        
        # Click the copy icon button
        buttons = reka_page.locator("button").all()
        for idx in range(min(len(buttons), 10)):
            try:
                buttons[idx].click(timeout=1000)
                time.sleep(0.5)
                out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"], capture_output=True, text=True)
                clip = (out.stdout or "").strip()
                if len(clip) >= 30 and not " " in clip:
                    print(f"    Testing Reka clipboard candidate from button {idx}: {fingerprint(clip)}")
                    r = requests.get("https://api.reka.ai/v1/models", headers={"Authorization": f"Bearer {clip}", "X-Api-Key": clip}, timeout=8)
                    if r.status_code == 200:
                        print(f"[+] VERIFIED Reka key: {fingerprint(clip)} (len={len(clip)})")
                        save_key("reka", clip, True, "Verified upstream models 200 OK")
                        w = wire(api, "reka", "Reka", clip)
                        print(f"    OmniRoute wire result: {w}")
                        break
            except Exception:
                pass
        reka_page.close()

if __name__ == "__main__":
    read_and_wire_both()
