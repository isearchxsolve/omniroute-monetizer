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
import requests

def test():
    user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    cmd = [
        chrome_exe,
        f"--user-data-dir={user_data_dir}",
        "--profile-directory=Profile 16",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    
    print("Launching Chrome manually (UI visible)...")
    proc = subprocess.Popen(cmd)
    
    print(f"Chrome PID: {proc.pid}")
    for i in range(10):
        time.sleep(1)
        try:
            r = requests.get("http://127.0.0.1:9222/json/version", timeout=1)
            print(f"Success! {r.json()}")
            break
        except Exception as e:
            print(f"Attempt {i}: {e}")
            
    time.sleep(5)
    proc.terminate()

if __name__ == "__main__":
    test()
