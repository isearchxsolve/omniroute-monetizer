import asyncio
import sys
from playwright.async_api import async_playwright
import os

async def interact(port, output_dir):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as e:
            print(f"Failed to connect to port {port}: {e}")
            return

        contexts = browser.contexts
        if not contexts:
            print("No contexts found")
            return
        
        page = None
        for p_ctx in contexts:
            if p_ctx.pages:
                page = p_ctx.pages[0]
                break
        
        if not page:
            page = await contexts[0].new_page()

        print(f"Connected to page on port {port}: {page.url}")
        
        if "about:blank" in page.url or "data:text/html" in page.url:
            print("Navigating to labs.google/fx/tools/flow...")
            await page.goto("https://labs.google/fx/tools/flow", wait_until="networkidle")
        
        screenshot1 = os.path.join(output_dir, f"before_click_{port}.png")
        await page.screenshot(path=screenshot1)
        print(f"Saved initial screenshot to {screenshot1}")

        # Look for the button
        try:
            button = page.locator("text=/Create with Google Flow|Continue with Google/i").first
            
            if await button.is_visible(timeout=5000):
                print("Found button, clicking...")
                await button.click()
                await page.wait_for_timeout(3000)
                
                screenshot2 = os.path.join(output_dir, f"after_click_{port}.png")
                await page.screenshot(path=screenshot2)
                print(f"Saved post-click screenshot to {screenshot2}")
            else:
                print("Button not found or not visible.")
        except Exception as e:
            print(f"Error finding/clicking button: {e}")

        await browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    port = sys.argv[1]
    out_dir = sys.argv[2]
    asyncio.run(interact(port, out_dir))
