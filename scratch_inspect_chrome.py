import subprocess
import time
import os

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = r"D:\omniroute-monetizer\state\automation_profiles"

port = 9223
profile_path = os.path.join(PROFILE_DIR, "niloy")
chrome_profile = "Profile 17"
url = "https://labs.google/fx/tools/flow"

print(f"[{port}] Launching Chrome...")
cmd = [
    CHROME_PATH,
    f"--remote-debugging-port={port}",
    "--remote-allow-origins=*",
    f"--user-data-dir={profile_path}",
    f"--profile-directory={chrome_profile}",
    "--no-first-run",
    "--no-default-browser-check",
    url
]

proc = subprocess.Popen(cmd)
print("Chrome launched. Keeping it open for inspection.")
time.sleep(60) # keep it alive for 60 seconds
proc.terminate()
