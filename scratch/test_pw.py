import os
import time
from playwright.sync_api import sync_playwright

def test():
    print("Starting Playwright sync...")
    user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    print(f"User data dir: {user_data_dir}")
    
    with sync_playwright() as pw:
        try:
            print("Launching persistent context...")
            context = pw.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                slow_mo=50,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--hide-crash-restore-bubble",
                    "--disable-sync",
                    "--no-default-browser-check"
                ]
            )
            print("Successfully launched!")
            pages = context.pages
            page = pages[0] if pages else context.new_page()
            print("Going to openrouter...")
            page.goto("https://openrouter.ai/keys", wait_until="domcontentloaded", timeout=15000)
            print("Loaded. Title:", page.title())
            time.sleep(2)
            context.close()
            print("Closed.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test()
