import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def test():
    print("Testing dedicated persistent context for OmniRoute Browser Engine...")
    profile_dir = Path(r"d:\omniroute-monetizer\state\browser_profile")
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-sync"
            ]
        )
        print("Successfully launched dedicated persistent context!")
        page = context.new_page()
        page.goto("https://openrouter.ai/keys", timeout=15000)
        print("Page loaded! Title:", page.title())
        context.close()
        print("Context closed cleanly.")

if __name__ == "__main__":
    test()
