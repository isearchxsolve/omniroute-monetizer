import subprocess
import time
import os
import sys

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = r"D:\omniroute-monetizer\state\automation_profiles"

seats = [
    {"port": 9223, "profile": "niloy", "chrome_profile": "Profile 17", "url": "https://labs.google/fx/tools/flow"},
    {"port": 9224, "profile": "seat2", "chrome_profile": "Default", "url": "https://labs.google/fx/tools/flow"},
    {"port": 9225, "profile": "seat3", "chrome_profile": "Default", "url": "https://labs.google/fx/tools/flow"}
]

def run_seat(seat):
    port = seat['port']
    profile_path = os.path.join(PROFILE_DIR, seat['profile'])
    chrome_profile = seat['chrome_profile']
    url = seat['url']
    
    print(f"[{port}] Launching Chrome...")
    # --profile-directory must be exactly as passed (e.g. "Profile 17")
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
    
    # Launch Chrome
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(8)  # Wait for it to load
    
    print(f"[{port}] Running scratch_flow_agent.py to sweep and grab...")
    agent_cmd = [
        sys.executable,
        r"D:\omniroute-monetizer\scratch_flow_agent.py",
        str(port)
    ]
    
    # Run the agent
    subprocess.run(agent_cmd, check=False)
    
    print(f"[{port}] Closing Chrome...")
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    time.sleep(2)

for s in seats:
    print(f"=== Processing Seat {s['port']} ===")
    run_seat(s)
    
print("All seats processed.")
