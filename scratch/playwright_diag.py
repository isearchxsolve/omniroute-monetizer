from playwright.sync_api import sync_playwright
import time

def main():
    print("Starting Playwright...", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        print("Navigating to login...", flush=True)
        page.goto('http://localhost:20128')
        time.sleep(2)
        
        # Check if we are on the login page by looking for the password input
        try:
            pwd = page.locator('input[type="password"]').first
            pwd.wait_for(state="visible", timeout=5000)
            print("Found password input. Logging in...", flush=True)
            pwd.fill('<REDACTED>')
            
            # Click Continue
            continue_btn = page.locator('button:has-text("Continue")').first
            continue_btn.click()
            time.sleep(3)
        except Exception as e:
            print(f"Skipping login (maybe already logged in or no input found): {e}", flush=True)

        # Go to Codex
        print("Navigating to codex...", flush=True)
        page.goto('http://localhost:20128/dashboard/providers/codex')
        time.sleep(3)
        
        dom = page.evaluate('document.body.outerHTML')
        with open('codex_dom.html', 'w', encoding='utf-8') as f:
            f.write(dom)
        print(f"Saved {len(dom)} bytes to codex_dom.html")
        page.screenshot(path='codex_diagnosis.png')
        
        # Openai
        print("Navigating to openai...", flush=True)
        page.goto('http://localhost:20128/dashboard/providers/openai')
        time.sleep(3)
        
        dom = page.evaluate('document.body.outerHTML')
        with open('openai_dom.html', 'w', encoding='utf-8') as f:
            f.write(dom)
        print(f"Saved {len(dom)} bytes to openai_dom.html")
        page.screenshot(path='openai_diagnosis.png')
        
        browser.close()
        print("Done.", flush=True)

if __name__ == "__main__":
    main()
