import asyncio
import sys
from playwright.async_api import async_playwright
import os

async def take_screenshot(port, output_dir):
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
        
        screenshot = os.path.join(output_dir, f"current_state_{port}.png")
        await page.screenshot(path=screenshot)
        print(f"Saved current screenshot to {screenshot}")

        await browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    port = sys.argv[1]
    out_dir = sys.argv[2]
    asyncio.run(take_screenshot(port, out_dir))
