"""Extract OpenAdapter key from dashboard via Playbook and query upstream models.
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

def pilot_openadapter():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        page = ctx.new_page()
        page.bring_to_front()
        
        print("[1] Navigating to https://dashboard.openadapter.in/keys ...")
        page.goto("https://dashboard.openadapter.in/keys", wait_until="domcontentloaded", timeout=25000)
        time.sleep(3)
        print(f"    URL: {page.url} | Title: {page.title()}")
        
        # Click "show" button
        print("[2] Looking for 'show' button...")
        show_btn = page.locator("button:has-text('show'), button:has-text('Show')").first
        if show_btn.count():
            print("    Clicking 'show' button...")
            show_btn.click()
            time.sleep(1)
        
        body = page.inner_text("body")
        key_match = re.search(r"\b(sk-[A-Za-z0-9_\-]{20,})\b", body)
        if not key_match:
            print("[-] Key not found in body after show. Trying clipboard or inputs...")
            inputs = page.locator("input, code").all()
            for inp in inputs:
                try:
                    val = inp.input_value() if inp.evaluate("el => el.tagName") == "INPUT" else inp.inner_text()
                    if re.match(r"^sk-[A-Za-z0-9_\-]{20,}$", val.strip()):
                        key_match = re.match(r"^sk-[A-Za-z0-9_\-]{20,}$", val.strip())
                        break
                except Exception:
                    pass
        
        if key_match:
            key = key_match.group(0).strip()
            print(f"[+] Successfully extracted OpenAdapter key: {fingerprint(key)} (len={len(key)})")
            
            # Query upstream models directly
            print("[3] Querying OpenAdapter upstream models...")
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            try:
                r = requests.get("https://api.openadapter.in/v1/models", headers=headers, timeout=10)
                print(f"    GET https://api.openadapter.in/v1/models -> HTTP {r.status_code}")
                if r.status_code == 200:
                    data = r.json()
                    models = [m.get("id") for m in data.get("data", [])]
                    print(f"    Available models ({len(models)}):")
                    for m in models:
                        print(f"      - {m}")
                    
                    # Test chat completion directly against openadapter with first 3 models
                    for m in models[:3]:
                        print(f"[*] Testing direct chat completion on upstream for model '{m}'...")
                        payload = {
                            "model": m,
                            "messages": [{"role": "user", "content": "respond with 'HELLO_OPENADAPTER' and nothing else"}],
                            "max_tokens": 10
                        }
                        cr = requests.post("https://api.openadapter.in/v1/chat/completions", headers=headers, json=payload, timeout=15)
                        print(f"    Status: {cr.status_code}")
                        if cr.status_code == 200:
                            print(f"    Response: {cr.json().get('choices', [{}])[0].get('message', {}).get('content')}")
                        else:
                            print(f"    Error: {cr.text[:200]}")
                else:
                    print(f"    Body: {r.text[:300]}")
            except Exception as e:
                print(f"    [-] Upstream request error: {e}")
        else:
            print("[-] Could not find key on OpenAdapter page.")
            print(f"    Body snippet: {body[:600]}")

if __name__ == "__main__":
    pilot_openadapter()
