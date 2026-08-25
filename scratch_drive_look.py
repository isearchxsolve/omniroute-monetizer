import sys
import os
import asyncio
import subprocess
import time

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = r"D:\omniroute-monetizer\state\automation_profiles"

port = 9223
profile_path = os.path.join(PROFILE_DIR, "niloy")
chrome_profile = "Profile 17"

print(f"[{port}] Launching Chrome...")
cmd = [
    CHROME_PATH,
    f"--remote-debugging-port={port}",
    "--remote-allow-origins=*",
    f"--user-data-dir={profile_path}",
    f"--profile-directory={chrome_profile}",
    "--no-first-run",
    "--no-default-browser-check"
]

proc = subprocess.Popen(cmd)
time.sleep(5)

# Setup env for drive.py
os.environ["DRIVE_CDP_PORT"] = str(port)
sys.path.append(r"D:\omniroute-monetizer\scripts\automation")
import drive

try:
    s = drive.Sess()
    drive.cmd_open(s, "https://labs.google/fx/tools/flow")
    time.sleep(10)
    drive.cmd_look(s)
finally:
    proc.terminate()
