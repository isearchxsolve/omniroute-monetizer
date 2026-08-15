import asyncio
import os
import sys
from playwright.async_api import async_playwright

async def find_dashboard():
    user_data_dir = os.path.abspath("state/browser_profile")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        urls_to_test = [
            "https://www.tokenrouter.com/keys",
            "https://www.tokenrouter.com/dashboard",
            "https://www.tokenrouter.com/settings"
        ]
        
        for url in urls_to_test:
            print(f"\nTesting {url} ...")
            await page.goto(url, wait_until="networkidle")
            content = await page.content()
            
            if "Page not found" in content or "404" in content:
                print(" -> 404 Not Found")
            else:
                print(" -> Looks valid!")
                await page.screenshot(path=f"artifacts/valid_url_{url.split('/')[-1]}.png")
                
        await context.close()

if __name__ == "__main__":
    asyncio.run(find_dashboard())
