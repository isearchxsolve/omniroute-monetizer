"""Minimal Playwright connect_over_cdp test — fast iteration on the connect hang."""
import asyncio, time
from playwright.async_api import async_playwright

async def main():
    t0 = time.time()
    async with async_playwright() as p:
        print(f"[{time.time()-t0:.1f}s] connecting...", flush=True)
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=60000)
        print(f"[{time.time()-t0:.1f}s] CONNECTED ok", flush=True)
        print("contexts:", len(b.contexts), flush=True)
        for ctx in b.contexts:
            print("  pages:", [pg.url for pg in ctx.pages], flush=True)
        await b.close()

asyncio.run(main())
