import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.async_api import async_playwright

async def screenshot_dashboard():
    user_data_dir = os.path.abspath("state/browser_profile")
    os.makedirs("artifacts", exist_ok=True)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/api-keys ...")
        await page.goto("https://www.tokenrouter.com/api-keys", wait_until="networkidle")
        await asyncio.sleep(3)
        
        await page.screenshot(path="artifacts/tokenrouter_dashboard.png", full_page=True)
        print("Screenshot saved to artifacts/tokenrouter_dashboard.png")
        
        # Click Create Key if it exists and screenshot again
        create_btn = await page.query_selector("button:has-text('Create'), button:has-text('New Key')")
        if create_btn:
            await create_btn.click()
            await asyncio.sleep(2)
            await page.screenshot(path="artifacts/tokenrouter_modal.png")
            print("Modal screenshot saved to artifacts/tokenrouter_modal.png")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(screenshot_dashboard())
