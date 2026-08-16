#!/usr/bin/env python3
import asyncio
import re
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

print("SCRIPT STARTING - HEADLESS TEST")

async def extract_tokenrouter_key() -> str:
    """
    Extracts the TokenRouter API key using persistent browser context.
    """
    print("Inside extract_tokenrouter_key function")
    user_data_dir = "state/browser_profile"
    target_url = "https://www.tokenrouter.com/"
    
    print(f"Using user data dir: {user_data_dir}")
    print(f"Target URL: {target_url}")
    
    async with async_playwright() as p:
        print("Launching persistent context (headless)")
        context: BrowserContext = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,  # HEADLESS MODE
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        try:
            print("Creating new page")
            page: Page = await context.new_page()
            print(f"Navigating to {target_url}")
            await page.goto(target_url, wait_until="networkidle")
            print("Navigation completed")
            
            # Handle Welcome Builders modal
            print("Handling welcome modal")
            await handle_welcome_modal(page)
            
            # Handle Google OAuth flow
            print("Handling Google OAuth")
            await handle_google_oauth(page, context)
            
            # Wait for dashboard to load
            print("Waiting for dashboard")
            await wait_for_dashboard(page)
            
            # Extract API key from DOM
            print("Extracting API key")
            api_key = await extract_api_key(page)
            
            if not api_key:
                raise Exception("API key not found on dashboard")
                
            print(f"API key extracted: {api_key}")
            return api_key
            
        except Exception as e:
            print(f"Error in extract_tokenrouter_key: {e}")
            raise
        finally:
            print("Closing context")
            await context.close()

async def handle_welcome_modal(page: Page) -> None:
    print("In handle_welcome_modal")
    try:
        modal = page.locator("text=Welcome Builders").first
        print("Waiting for Welcome Builders modal")
        await modal.wait_for(state="visible", timeout=5000)
        print("Modal found")
        
        tos_checkbox = page.locator("input[type='checkbox']").filter(has_text=re.compile("Terms.*Conditions", re.I))
        if await tos_checkbox.count() > 0:
            await tos_checkbox.check()
        else:
            tos_label = page.locator("label:has-text('I agree to the Terms and Conditions')")
            if await tos_label.count() > 0:
                await tos_label.locator("input[type='checkbox']").check()
            else:
                checkboxes = page.locator("input[type='checkbox']")
                if await checkboxes.count() > 0:
                    await checkboxes.first.check()
        
        google_btn = page.locator("button:has-text('Sign in with Google'), button:has-text('Continue with Google'), button:has-text('Google')")
        await google_btn.first.click(timeout=5000)
        
        await modal.wait_for(state="hidden", timeout=5000)
        print("Welcome modal handled")
    except PlaywrightTimeoutError:
        print("Welcome modal not present (continuing)")
        pass

async def handle_google_oauth(page: Page, context: BrowserContext) -> None:
    print("In handle_google_oauth")
    try:
        print("Waiting for popup or navigation")
        async with context.expect_page() as popup_info:
            await page.wait_for_timeout(3000)
        
        popup_page = await popup_info.value
        print("Popup detected")
        
        try:
            await popup_page.wait_for_url("**/accounts/**", timeout=15000)
            await popup_page.wait_for_url("**/tokenrouter.com/**", timeout=20000)
        except:
            pass
        
        await popup_page.wait_for_event("close", timeout=30000)
        print("Popup closed")
        
    except TimeoutError:
        print("No popup detected, waiting for same-tab redirect...")
        pass
    
    print("Waiting for main page navigation")
    await page.wait_for_url("**/tokenrouter.com/**", wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(5000)

async def wait_for_dashboard(page: Page) -> None:
    print("In wait_for_dashboard")
    dashboard_indicators = [
        "text=Dashboard",
        "text=API Keys",
        "text=Your API Key",
        "[data-testid='api-key']",
        ".api-key-display"
    ]
    
    for indicator in dashboard_indicators:
        try:
            print(f"Waiting for: {indicator}")
            await page.locator(indicator).first.wait_for(state="visible", timeout=10000)
            print(f"Found: {indicator}")
            return
        except TimeoutError:
            continue
    
    print("Fallback: network idle")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(3000)

async def extract_api_key(page: Page) -> str:
    print("In extract_api_key")
    await page.wait_for_timeout(3000)
    
    key_patterns = [
        r'sk-[\w-]+',
        r'tr-[\w-]+',
        r'tokenrouter[\w-]+',
    ]
    
    for pattern in key_patterns:
        print(f"Searching pattern: {pattern}")
        elements = await page.locator(f"xpath=//*[contains(text(), '{pattern}')]").all()
        for element in elements:
            if await element.is_visible():
                text = await element.text_content()
                match = re.search(pattern, text)
                if match:
                    key = match.group(0)
                    if len(key) > 10 and (key.startswith('sk-') or key.startswith('tr-')):
                        print(f"Found key: {key}")
                        return key
    
    input_selectors = [
        "input[readonly]",
        ".api-key-input",
        "[data-testid='api-key-input']",
        "code",
        ".key-display"
    ]
    
    for selector in input_selectors:
        try:
            element = page.locator(selector).first
            if await element.count() > 0 and await element.is_visible():
                value = await element.input_value() if "input" in selector else await element.text_content()
                for pattern in key_patterns:
                    match = re.search(pattern, value)
                    if match:
                        key = match.group(0)
                        if len(key) > 10 and (key.startswith('sk-') or key.startswith('tr-')):
                            print(f"Found key via input: {key}")
                            return key
        except:
            continue
    
    print("No API key found")
    return None

async def main():
    try:
        print("Starting main")
        key = await extract_tokenrouter_key()
        print(f"SUCCESS: {key}")
        with open("tokenrouter_key.txt", "w") as f:
            f.write(key)
        print("Saved to tokenrouter_key.txt")
    except Exception as e:
        print(f"FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    print("Script starting")
    asyncio.run(main())
    print("Script completed")