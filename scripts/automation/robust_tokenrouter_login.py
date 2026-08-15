import asyncio
import os
import sys
import re
from playwright.async_api import async_playwright

async def robust_tokenrouter_login():
    user_data_dir = os.path.abspath("state/browser_profile")
    
    print("========================================================")
    print("   ROBUST PLAYWRIGHT AUTOMATION (ENGINEERING STANDARD)  ")
    print("========================================================")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--start-maximized"]
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/ ...")
        await page.goto("https://www.tokenrouter.com/", wait_until="networkidle")
        
        # Check if modal is already open, if not, open it
        try:
            modal = await page.query_selector("text='Welcome Builders'")
            if not modal:
                print("Clicking 'Sign In' to open modal...")
                await page.evaluate("document.evaluate(\"//button[contains(text(), 'Sign In')]\", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue.click()")
                await asyncio.sleep(2)
        except Exception as e:
            pass
            
        try:
            print("Locating terms and conditions checkbox...")
            # We will use javascript evaluate to find the checkbox and check it to avoid pointer interception
            await page.evaluate("""
                const cb = document.querySelector("input[type='checkbox']");
                if (cb && !cb.checked) {
                    cb.click();
                }
            """)
            print("Checked terms checkbox.")
            await asyncio.sleep(1)
            
            print("Locating 'Sign in with Google' button...")
            # Google button usually has an svg or text, or we can find it by finding the button that has 'G' or is adjacent to X
            await page.evaluate("""
                // Find buttons in the modal
                const buttons = Array.from(document.querySelectorAll("button"));
                for (let b of buttons) {
                    if (b.innerHTML.includes('M22.56') || b.innerHTML.includes('google') || (b.querySelector('svg') && !b.innerText.includes('Sign In'))) {
                        b.click();
                        break;
                    }
                }
            """)
            print("Clicked Google Sign-In button.")
            
            print("Waiting for Google authentication sequence...")
            await asyncio.sleep(15) # Wait for redirects
            
        except Exception as e:
            print(f"Error interacting with modal: {e}")
            
        # 5. Extract Key
        print("Extracting Key from Dashboard...")
        extracted_key = None
        for _ in range(5):
            content = await page.content()
            matches = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}|tr-[a-zA-Z0-9_\-]{20,}', content)
            for m in matches:
                if not any(dummy in m for dummy in ["sk-tokenrouter-free", "language", "translate", "tr-header"]):
                    extracted_key = m
                    break
            if extracted_key:
                break
            await asyncio.sleep(2)
            
        if extracted_key:
            print(f"\n[FOUND KEY]: {extracted_key[:6]}...{extracted_key[-4:]}")
        else:
            print("Failed to find key in DOM.")
            
        await context.close()

if __name__ == "__main__":
    asyncio.run(robust_tokenrouter_login())
