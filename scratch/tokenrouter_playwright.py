import sys
sys.stdout.reconfigure(encoding='utf-8')
import asyncio
import os
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        user_data_dir = os.path.abspath("state/browser_profile")
        print(f"Launching persistent browser context from {user_data_dir}...")
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/...")
        await page.goto("https://www.tokenrouter.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        print("Taking initial screenshot...")
        await page.screenshot(path="scratch/tokenrouter_home.png")
        
        # Check what modals exist
        modals = await page.query_selector_all(".fixed, [role='dialog'], modal")
        print(f"Found {len(modals)} modal elements")
        for m in modals:
            txt = (await m.inner_text()).strip()
            print("Modal text:", txt[:200])

        # Click Sign In or Sign Up
        signin = await page.query_selector("button:has-text('Sign In'), a:has-text('Sign In')")
        if signin:
            print("Clicking Sign In with force=True...")
            await signin.click(force=True)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="scratch/tokenrouter_signin.png")
            print("After Sign In click URL:", page.url)
            
            # Print form inputs and buttons in modal
            modal_buttons = await page.query_selector_all("button, a")
            print("--- MODAL ACTION BUTTONS ---")
            for b in modal_buttons:
                txt = (await b.inner_text()).strip()
                if any(k in txt.lower() for k in ["google", "github", "sign in", "sign up", "continue", "submit"]):
                    print(f"Modal Button: {txt}")
                    
        await context.close()

if __name__ == "__main__":
    asyncio.run(run())
