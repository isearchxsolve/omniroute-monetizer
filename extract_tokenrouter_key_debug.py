#!/usr/bin/env python3
import asyncio
import re
from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeoutError

print("SCRIPT STARTING - DEBUG VERSION")

async def extract_tokenrouter_key() -> str:
    """
    Extracts the TokenRouter API key using persistent browser context.
    Returns the API key string if found, otherwise raises an exception.
    """
    print("Inside extract_tokenrouter_key function")
    user_data_dir = "state/browser_profile"
    target_url = "https://www.tokenrouter.com/"
    
    print(f"Using user data dir: {user_data_dir}")
    print(f"Target URL: {target_url}")
    
    async with async_playwright() as p:
        print("Launching persistent context")
        # Launch persistent context with the pre-authenticated profile
        context: BrowserContext = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # Visible for debugging
            args=["--start-maximized"]
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
    """Handles the 'Welcome Builders' modal by checking TOS and clicking Google sign-in."""
    print("In handle_welcome_modal")
    try:
        # Wait for modal to appear (if present) with a short timeout
        modal = page.locator("text=Welcome Builders").first
        print("Waiting for Welcome Builders modal")
        await modal.wait_for(state="visible", timeout=3000)
        print("Modal found")
        
        # Check Terms and Conditions checkbox
        tos_checkbox = page.locator("input[type='checkbox']").filter(has_text=re.compile("Terms.*Conditions", re.I))
        if await tos_checkbox.count() > 0:
            await tos_checkbox.check()
        else:
            # Fallback: try to find checkbox by proximity to text
            tos_label = page.locator("label:has-text('I agree to the Terms and Conditions')")
            if await tos_label.count() > 0:
                await tos_label.locator("input[type='checkbox']").check()
            else:
                # Last resort: find any checkbox near the modal
                checkboxes = page.locator("input[type='checkbox']")
                if await checkboxes.count() > 0:
                    await checkboxes.first.check()
        
        # Click Sign in with Google button
        google_btn = page.locator("button:has-text('Sign in with Google'), button:has-text('Continue with Google'), button:has-text('Google')")
        await google_btn.first.click(timeout=3000)
        
        # Wait for modal to disappear
        await modal.wait_for(state="hidden", timeout=3000)
        print("Welcome modal handled")
    except PlaywrightTimeoutError:
        # Modal not present, which is fine
        print("Welcome modal not present or timed out (continuing)")
        pass

async def handle_google_oauth(page: Page, context: BrowserContext) -> None:
    """Handles Google OAuth flow - either popup or redirect."""
    print("In handle_google_oauth")
    # Wait for potential popup or navigation
    try:
        # Wait for either a new page (popup) or navigation in current page
        print("Waiting for popup or navigation")
        async with context.expect_page() as popup_info:
            # Give time for OAuth to initiate
            await page.wait_for_timeout(2000)
        
        # If we get here, a popup was expected
        popup_page = await popup_info.value
        print("Popup detected, waiting for Google sign-in completion...")
        
        # Wait for popup to close (sign-in successful) or navigate to a known success URL
        try:
            await popup_page.wait_for_url("**/accounts/**", timeout=10000)  # Google accounts URL during auth
            await popup_page.wait_for_url("**/tokenrouter.com/**", timeout=15000)  # Redirect back
        except:
            pass  # Continue even if timeout
        
        # Wait for popup to close
        await popup_page.wait_for_event("close", timeout=15000)
        print("Popup closed, returning to main window")
        
    except TimeoutError:
        # No popup detected, assume same-tab redirect
        print("No popup detected, waiting for same-tab redirect...")
        pass
    
    # Wait for navigation to complete in main page
    print("Waiting for main page navigation to complete")
    await page.wait_for_url("**/tokenrouter.com/**", wait_until="networkidle", timeout=15000)
    
    # Additional wait for any post-login redirects
    print("Additional wait for post-login redirects")
    await page.wait_for_timeout(3000)

async def wait_for_dashboard(page: Page) -> None:
    """Waits for the TokenRouter dashboard to load after login."""
    print("In wait_for_dashboard")
    # Wait for common dashboard elements
    dashboard_indicators = [
        "text=Dashboard",
        "text=API Keys",
        "text=Your API Key",
        "[data-testid='api-key']",
        ".api-key-display"
    ]
    
    for indicator in dashboard_indicators:
        try:
            print(f"Waiting for dashboard indicator: {indicator}")
            await page.locator(indicator).first.wait_for(state="visible", timeout=5000)
            print(f"Found dashboard indicator: {indicator}")
            return
        except TimeoutError:
            print(f"Timeout waiting for indicator: {indicator}")
            continue
    
    # Fallback: wait for network idle and assume we're on dashboard
    print("Fallback: waiting for network idle")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)
    print("Dashboard wait completed")

async def extract_api_key(page: Page) -> str:
    """Extracts the API key from the dashboard DOM."""
    print("In extract_api_key")
    # Wait for key to be visible
    await page.wait_for_timeout(2000)
    
    # Try multiple strategies to find the API key
    key_patterns = [
        r'sk-[\w-]+',  # sk_ format
        r'tr-[\w-]+',  # tr_ format
        r'tokenrouter[\w-]+',  # alternative format
    ]
    
    # Strategy 1: Look for text matching patterns in visible elements
    for pattern in key_patterns:
        print(f"Strategy 1: Searching for pattern: {pattern}")
        elements = await page.locator(f"xpath=//*[contains(text(), '{pattern}')]").all()
        for element in elements:
            if await element.is_visible():
                text = await element.text_content()
                match = re.search(pattern, text)
                if match:
                    key = match.group(0)
                    # Validate key length and format
                    if len(key) > 10 and (key.startswith('sk-') or key.startswith('tr-')):
                        print(f"Found API key via strategy 1: {key}")
                        return key
    
    # Strategy 2: Check input fields and code blocks
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
                            print(f"Found API key via strategy 2: {key}")
                            return key
        except:
            continue
    
    # Strategy 3: Extract from network responses (if key was sent in API call)
    # This would require request/response interception - more complex
    # For now, we rely on DOM extraction
    
    print("No API key found")
    return None

async def main():
    try:
        print("Starting main function")
        key = await extract_tokenrouter_key()
        print(f"Successfully extracted TokenRouter API key: {key}")
        # Optionally save to file or environment variable
        with open("tokenrouter_key.txt", "w") as f:
            f.write(key)
        print("API key saved to tokenrouter_key.txt")
    except Exception as e:
        print(f"Failed to extract API key: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    print("Script starting")
    asyncio.run(main())
    print("Script completed")