# --- 2026-08-22 CHROME INCIDENT GUARD (AGENTS.md 14.1) -------------------------------
# This file targets the operator's LIVE Chrome profile. That is what revoked all four
# Google sessions, over and over. The guard below makes the launch fail loudly instead.
# Do not remove it. Give automation its own profile: chrome_live_guard.safe_profile_dir().
import os as _guard_os
import sys as _guard_sys
_guard_sys.path.insert(0, _guard_os.path.join(
    _guard_os.path.dirname(_guard_os.path.dirname(_guard_os.path.abspath(__file__))),
    "scripts", "automation"))
try:
    import chrome_live_guard as _chrome_live_guard
    _chrome_live_guard.install()
except Exception as _guard_err:      # never let the guard itself be the crash
    print("FATAL: chrome_live_guard could not load:", _guard_err)
    print("Refusing to run, because this script points at the live Chrome profile.")
    raise SystemExit(3)
# -------------------------------------------------------------------------------------

import os
import subprocess
import time
from playwright.sync_api import sync_playwright

def test():
    user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    cmd = [
        chrome_exe,
        f"--user-data-dir={user_data_dir}",
        "--profile-directory=Profile 16",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled"
    ]
    
    print("Launching Chrome manually (UI visible)...")
    proc = subprocess.Popen(cmd)
    
    time.sleep(5)
    print(f"Chrome PID: {proc.pid}")
    
    if proc.poll() is not None:
        print(f"Chrome exited with code {proc.returncode}")
        return

    print("Starting Playwright sync...")
    with sync_playwright() as pw:
        try:
            print("Connecting over CDP...")
            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
            print("Successfully connected!")
            context = browser.contexts[0]
            pages = context.pages
            page = pages[0] if pages else context.new_page()
            print("Going to openrouter...")
            page.goto("https://openrouter.ai/keys", wait_until="domcontentloaded", timeout=15000)
            print("Loaded. Title:", page.title())
            time.sleep(2)
            browser.close()
            print("Closed.")
        except Exception as e:
            print(f"Error: {e}")
            
    try:
        proc.terminate()
    except:
        pass

if __name__ == "__main__":
    test()
