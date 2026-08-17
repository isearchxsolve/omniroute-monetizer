import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = b.contexts[0]
        for pg in ctx.pages:
            if "huggingface.co/join" in pg.url:
                await pg.bring_to_front()
                print("brought /join to front:", pg.url)
                return
        print("no /join tab found")

asyncio.run(main())
