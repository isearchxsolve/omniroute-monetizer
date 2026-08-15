import os
import subprocess
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

def test():
    print("Starting Playwright sync...")
    src_base = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
    src_profile = src_base / "Profile 16"
    dest_dir = Path(os.path.expandvars(r"%TEMP%\OmniRouteProfile"))
    dest_profile = dest_dir / "Default"
    
    print("Running Robocopy...")
    # Robocopy is extremely fast. We ignore cache folders to save time.
    subprocess.run([
        "robocopy", str(src_profile), str(dest_profile), "/E", "/MT:16",
        "/XD", "Cache", "Code Cache", "DawnCache", "GPUCache", "Service Worker\\CacheStorage",
        "/R:0", "/W:0"
    ], stdout=subprocess.DEVNULL)
    
    # Copy Local State for os_crypt
    print("Copying Local State...")
    import shutil
    shutil.copy2(src_base / "Local State", dest_dir / "Local State")
    
    print("Launching persistent context...")
    with sync_playwright() as pw:
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(dest_dir),
                headless=True,
                slow_mo=50,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--hide-crash-restore-bubble",
                    "--disable-sync",
                    "--no-default-browser-check",
                    "--disable-extensions"
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
