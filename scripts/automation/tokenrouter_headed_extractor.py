import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
import re
import requests
import subprocess
from playwright.async_api import async_playwright

def validate_key(key: str) -> bool:
    if not key or len(key) < 15:
        return False
    try:
        r = requests.get("https://api.tokenrouter.com/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=8)
        print(f"  Validating key '{key[:8]}...': HTTP {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"  Validation request error: {e}")
        return False

async def run_headed_extractor():
    user_data_dir = os.path.abspath("state/browser_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    
    print("========================================================")
    print("       TOKENROUTER HEADED KEY EXTRACTION ENGINE         ")
    print("========================================================")
    print("Launching visible browser window on your desktop...")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--start-maximized"]
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/ ...")
        await page.goto("https://www.tokenrouter.com/", wait_until="domcontentloaded")
        
        print("\n>>> BROWSER IS NOW OPEN ON YOUR SCREEN <<<")
        print("Please Sign In / Sign Up on TokenRouter.")
        print("The script is waiting and will intercept your real API key automatically once you create/view it.\n")
        
        verified_key = None
        
        for turn in range(150): # Wait up to 5 minutes (150 * 2s)
            current_url = page.url
            
            # Check clipboard or inputs or text
            try:
                # Check all inputs and pre/code elements
                elements = await page.query_selector_all("input, textarea, code, pre, span, div")
                for el in elements:
                    val = (await el.get_attribute("value") or await el.inner_text() or "").strip()
                    if ("sk-" in val or "tr-" in val) and len(val) >= 25 and not any(k in val for k in ["tokenrouter-free", "language", "translate"]):
                        # Test if it's a real live key
                        if validate_key(val):
                            verified_key = val
                            print(f"\n>>> LIVE AUTHENTICATED KEY CONFIRMED (HTTP 200): {verified_key[:8]}... <<<")
                            break
            except Exception:
                pass
                
            if verified_key:
                break
                
            await asyncio.sleep(2)
            
        storage_state_path = "state/browser_profile/storage_state.json"
        await context.storage_state(path=storage_state_path)
        print(f"Saved storage state to {storage_state_path}")
        
        await context.close()
        
        if verified_key:
            print("\n========================================================")
            print("          INJECTING VERIFIED KEY INTO SYSTEM            ")
            print("========================================================")
            cmd = f'cmdkey /generic:"zed:url=https://api.tokenrouter.com/v1" /user:"Bearer" /pass:"{verified_key}"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            print("Windows Credential Manager:", res.stdout.strip())
            print("TOKENROUTER_AUTOMATION_COMPLETED_SUCCESSFULLY")
        else:
            print("\nWindow closed or timeout reached before a valid key was intercepted.")

if __name__ == "__main__":
    asyncio.run(run_headed_extractor())
