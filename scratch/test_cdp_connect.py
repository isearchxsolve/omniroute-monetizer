import time
from playwright.sync_api import sync_playwright

def test():
    print("Starting Playwright sync...")
    with sync_playwright() as pw:
        try:
            print("Connecting over CDP...")
            browser = pw.chromium.connect_over_cdp("http://localhost:9222")
            print("Successfully connected!")
            context = browser.contexts[0]
            pages = context.pages
            page = pages[0] if pages else context.new_page()
            print("Going to openrouter...")
            page.goto("https://openrouter.ai/keys", wait_until="domcontentloaded", timeout=15000)
            print(page.url)
            print("Loaded. Closing...")
            browser.close()
            print("Closed.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test()
