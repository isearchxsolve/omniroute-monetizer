import asyncio
import json
import time
import os
import sys
from playwright.async_api import async_playwright

async def grab_flow_session(port, host_override="labs.google"):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as e:
            print(f"[{port}] Failed to connect: {e}")
            return
            
        contexts = browser.contexts
        if not contexts:
            return
            
        target_page = None
        for p in contexts[0].pages:
            if "labs.google" in p.url:
                target_page = p
                break
        
        if not target_page:
            target_page = contexts[0].pages[0] if contexts[0].pages else await contexts[0].new_page()
            await target_page.goto("https://labs.google/fx/tools/flow")
            
        page = target_page
        print(f"[{port}] Connected to page: {page.url}")
        
        captured_req = None
        
        # Setup network interception
        async def on_request(request):
            nonlocal captured_req
            if request.method in ["POST", "PUT"]:
                url = request.url.lower()
                if not any(k in url for k in ["google-analytics", "telemetry", "collect", "play.google"]):
                    if "video" in url or "generate" in url or "fx" in url:
                        print(f"[{port}] Intercepted request: {request.url}")
                        try:
                            post_data = request.post_data
                            headers = request.headers
                            captured_req = {
                                "method": request.method,
                                "url": request.url,
                                "headers": headers,
                                "post_data": post_data
                            }
                        except Exception:
                            pass
        
        page.on("request", on_request)
        
        # Navigate or interact with Flow
        await page.bring_to_front()
        time.sleep(2)
        
        # Find the textarea and type
        try:
            # Try to click "Create with Google Flow" button if it exists
            create_btn = page.locator("button:has-text('Create with Google Flow')")
            if await create_btn.count() > 0:
                print(f"[{port}] Clicking 'Create with Google Flow' button...")
                await create_btn.first.click()
                await page.wait_for_timeout(2000)

            print(f"[{port}] Typing prompt...")
            # Look for textarea
            textarea = page.locator("textarea").first
            await textarea.fill("A cinematic 4k highly detailed video of a red fox running through snow")
            await page.wait_for_timeout(1000)
            
            # Look for generate button. It might be an arrow or "Generate"
            # It's usually a button near the textarea or a div with role button
            generate_btn = page.locator("button[aria-label*='Generate'], button:has-text('Generate'), button:has-text('Create'), button svg").last
            print(f"[{port}] Clicking generate...")
            await generate_btn.click(force=True)
            
        except Exception as e:
            print(f"[{port}] UI Interaction failed: {e}")
            
        # Wait up to 10s for the network request
        for _ in range(20):
            if captured_req:
                break
            await page.wait_for_timeout(500)
            
        if captured_req:
            # Save it
            secrets_dir = os.path.join(r"D:\omniroute-monetizer\state\secrets")
            os.makedirs(secrets_dir, exist_ok=True)
            sess_file = os.path.join(secrets_dir, f"session_{host_override.replace('.','_')}.json")
            
            existing = {}
            if os.path.exists(sess_file):
                try:
                    with open(sess_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
                    
            existing["host"] = host_override
            existing["recorded_exchange"] = captured_req
            existing["updated_at"] = int(time.time())
            
            with open(sess_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
                
            print(f"[{port}] Saved recorded exchange to {sess_file}")
        else:
            print(f"[{port}] No relevant POST request intercepted.")
            
        await browser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(grab_flow_session(sys.argv[1]))
