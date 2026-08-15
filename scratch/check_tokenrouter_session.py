import asyncio
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import json
from playwright.async_api import async_playwright

async def inspect_tokenrouter():
    user_data_dir = os.path.abspath("state/browser_profile")
    print(f"Connecting to persistent context at {user_data_dir}...")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            args=["--no-sandbox", "--disable-gpu"]
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        print("Navigating to https://www.tokenrouter.com/...")
        await page.goto("https://www.tokenrouter.com/", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        current_url = page.url
        print("Current URL:", current_url)
        
        # Check cookies
        cookies = await context.cookies()
        tr_cookies = [c for c in cookies if "tokenrouter" in c.get("domain", "")]
        print(f"Found {len(tr_cookies)} TokenRouter cookies: {[c.get('name') for c in tr_cookies]}")
        
        # Check text on page
        body_text = await page.inner_text("body")
        print("Body text sample (first 400 chars):")
        print(body_text[:400])
        
        # Check if user is logged in
        nav_elements = await page.query_selector_all("a, button")
        auth_elements = []
        for el in nav_elements:
            txt = (await el.inner_text()).strip()
            href = await el.get_attribute("href")
            if any(k in txt.lower() for k in ["dashboard", "key", "api", "profile", "account", "logout", "sign out", "billing"]):
                auth_elements.append(f"Text: {txt} | Href: {href}")
                
        print(f"--- RELEVANT AUTH/DASHBOARD ELEMENTS ({len(auth_elements)}) ---")
        for ae in auth_elements:
            print(" ", ae)
            
        # Try direct navigation to common API key routes
        key_routes = [
            "https://www.tokenrouter.com/dashboard",
            "https://www.tokenrouter.com/keys",
            "https://www.tokenrouter.com/api-keys",
            "https://www.tokenrouter.com/settings/api-keys",
            "https://www.tokenrouter.com/account"
        ]
        for route in key_routes:
            print(f"Checking route: {route}...")
            await page.goto(route, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            print(f"  Result URL: {page.url}")
            if page.url != "https://www.tokenrouter.com/" and page.url != "https://www.tokenrouter.com/sign-in":
                # Check for API keys in DOM
                inputs = await page.query_selector_all("input, code, span, pre")
                for inp in inputs:
                    val = await inp.get_attribute("value") or await inp.inner_text()
                    if val and ("sk-" in val or "tr-" in val):
                        print(f"  POTENTIAL KEY FOUND on {route}: {val}")
                        
        await context.close()

if __name__ == "__main__":
    asyncio.run(inspect_tokenrouter())
