from playwright.async_api import async_playwright
import asyncio

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        print('Browser launched')
        await browser.close()
        await asyncio.sleep(0.1)

asyncio.run(test())
print('Test completed')