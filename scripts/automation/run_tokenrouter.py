import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import re
import requests
import subprocess
import datetime
from playwright.async_api import async_playwright

async def run_tokenrouter_automation():
    user_data_dir = os.path.abspath("state/browser_profile")
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    key_name = f"omniroute-auto-{timestamp}"
    
    print("========================================================")
    print("       TOKENROUTER FULL AUTOMATION ENGINE               ")
    print("========================================================")
    
    async with async_playwright() as p:
        # We will use headless=False so user can see the magic!
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/api-keys ...")
        await page.goto("https://www.tokenrouter.com/api-keys", wait_until="domcontentloaded")
        
        # Give it a second to hydrate
        await asyncio.sleep(2)
        
        content = await page.content()
        if "sign in" in content.lower():
            print("[!] Authentication Wall Detected! Session might be expired.")
            await context.close()
            return
            
        print("Session valid! Executing 'Create New Key' flow...")
        extracted_key = None
        
        try:
            # TokenRouter specific DOM flow (generic fallback based on common dashboard patterns)
            # Find a button to create key
            create_btn = await page.query_selector("button:has-text('Create'), button:has-text('New Key'), button:has-text('Generate')")
            if create_btn:
                print("Clicking Create Key button...")
                await create_btn.click()
                await asyncio.sleep(1)
                
                # Check if there is a name input
                name_input = await page.query_selector("input[name='name'], input[placeholder*='name' i]")
                if name_input:
                    print(f"Filling key name: {key_name}")
                    await name_input.fill(key_name)
                    
                # Click the submit/create button in the modal
                submit_btn = await page.query_selector("button:has-text('Confirm'), button:has-text('Submit'), button[type='submit']")
                if submit_btn:
                    await submit_btn.click()
                    await asyncio.sleep(2)
            
            # Now we hunt for the key in the DOM!
            print("Hunting for the generated TokenRouter key...")
            for _ in range(10):
                content = await page.content()
                matches = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}|tr-[a-zA-Z0-9_\-]{20,}', content)
                for m in matches:
                    if not any(dummy in m for dummy in ["sk-tokenrouter-free", "language", "translate"]):
                        extracted_key = m
                        break
                if extracted_key:
                    break
                await asyncio.sleep(1)
                
            if not extracted_key:
                # Check inputs
                inputs = await page.query_selector_all("input, textarea, code, pre")
                for inp in inputs:
                    val = (await inp.get_attribute("value") or await inp.inner_text() or "").strip()
                    if ("sk-" in val or "tr-" in val) and len(val) >= 20:
                        if not any(dummy in val for dummy in ["sk-tokenrouter-free", "language"]):
                            extracted_key = val
                            break
                            
        except Exception as e:
            print(f"Automation error: {e}")
            
        await context.storage_state(path="state/browser_profile/storage_state.json")
        await context.close()
        
        if extracted_key:
            print(f"\n[FOUND KEY]: {extracted_key[:6]}...{extracted_key[-4:]}")
            print("\n========================================================")
            print("          VALIDATING & INJECTING EXTRACTED KEY          ")
            print("========================================================")
            
            headers = {"Authorization": f"Bearer {extracted_key}"}
            try:
                r = requests.get("https://api.tokenrouter.com/v1/models", headers=headers, timeout=10)
                print(f"Live validation status: {r.status_code}")
                if r.status_code == 200:
                    print("SUCCESS! Authenticated 200 OK against api.tokenrouter.com")
                    
                    cmd = f'cmdkey /generic:"zed:url=https://api.tokenrouter.com/v1" /user:"Bearer" /pass:"{extracted_key}"'
                    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                    print("Windows Credential Manager:", res.stdout.strip())
                else:
                    print(f"Validation failed. Response: {r.text[:200]}")
            except Exception as e:
                print(f"Validation error: {e}")
        else:
            print("\nFailed to extract the key from the DOM.")

if __name__ == "__main__":
    asyncio.run(run_tokenrouter_automation())
