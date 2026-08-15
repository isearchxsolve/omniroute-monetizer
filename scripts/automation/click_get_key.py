import asyncio
import os
from playwright.async_api import async_playwright

async def find_button_link():
    user_data_dir = os.path.abspath("state/browser_profile")
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/ ...")
        await page.goto("https://www.tokenrouter.com/", wait_until="networkidle")
        
        btn = await page.query_selector("text='Get API Key'")
        if btn:
            # Try to get href if it's a link
            href = await btn.get_attribute("href")
            print(f"Href: {href}")
            
            # Click it and see where it goes
            print("Clicking 'Get API Key'...")
            await btn.click()
            await asyncio.sleep(3)
            
            print(f"New URL: {page.url}")
            await page.screenshot(path="artifacts/after_click_get_api_key.png")
            print("Saved screenshot to artifacts/after_click_get_api_key.png")
            
            # Print body text to see what it is
            content = await page.inner_text("body")
            print(f"Body text snippet:\n{content[:500]}")
        else:
            print("Could not find 'Get API Key' text.")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(find_button_link())
