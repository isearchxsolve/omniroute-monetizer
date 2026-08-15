import asyncio
import os
import sys
from playwright.async_api import async_playwright

async def autonomous_tokenrouter_extractor():
    user_data_dir = os.path.abspath("state/browser_profile")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        print("Navigating to https://www.tokenrouter.com/ (Logged In State) ...")
        await page.goto("https://www.tokenrouter.com/", wait_until="networkidle")
        
        # 1. Close promo banner if present
        try:
            close_btn = await page.query_selector("div.cursor-pointer >> svg")
            if close_btn:
                await close_btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass
            
        print("Clicking 'Get API Key' on the homepage...")
        # Since we are logged in, clicking this should show the key!
        try:
            await page.evaluate("""
                const buttons = Array.from(document.querySelectorAll("button, a"));
                for (let b of buttons) {
                    if (b.innerText.includes('Get API Key')) {
                        b.click();
                        break;
                    }
                }
            """)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Error clicking Get API Key: {e}")
            
        print("Extracting potential keys...")
        
        # Dump any text containing 'sk-' or 'tr-' from inputs or body
        inputs = await page.query_selector_all("input")
        for i, inp in enumerate(inputs):
            val = await inp.get_attribute("value")
            if val and ('sk-' in val or 'tr-' in val):
                print(f"INPUT VALUE MATCH: {val}")
                
        body = await page.inner_text("body")
        for line in body.split('\n'):
            if 'sk-' in line or 'tr-' in line:
                if 'tr-header' not in line and 'sk-tokenrouter' not in line:
                    print(f"BODY MATCH: {line.strip()}")
                
        # Take a screenshot to verify what happened
        os.makedirs("artifacts", exist_ok=True)
        await page.screenshot(path="artifacts/final_key_modal.png")
        print("Screenshot saved to artifacts/final_key_modal.png")

        await context.close()

if __name__ == "__main__":
    asyncio.run(autonomous_tokenrouter_extractor())
