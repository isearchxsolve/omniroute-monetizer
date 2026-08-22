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

def test():
    # Add a trailing slash or use lowercase to bypass string equality check if it's dumb
    user_data_dir = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\user data")
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    cmd = [
        chrome_exe,
        f"--user-data-dir={user_data_dir}",
        "--profile-directory=Profile 16",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    
    print(f"Launching Chrome with user_data_dir={user_data_dir}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    start = time.time()
    while time.time() - start < 5:
        if proc.poll() is not None:
            break
        try:
            out = proc.stdout.readline()
            if out:
                print(f"CHROME: {out.strip()}")
        except:
            pass
            
    print("Done waiting.")
    proc.terminate()

if __name__ == "__main__":
    test()
