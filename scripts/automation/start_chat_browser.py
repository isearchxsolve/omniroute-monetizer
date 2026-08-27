import subprocess
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chrome_no_discard import NO_DISCARD_FLAGS  # stop Chrome discarding idle tabs

chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = r"D:\omniroute-monetizer\state\automation_profiles\providers"
urls = [
    "https://arena.lmsys.org",
    "https://duckduckgo.com/ai",
    "https://huggingface.co/chat",
    "https://poe.com",
    "https://www.phind.com",
    "https://www.blackbox.ai"
]

cmd = [
    "cmd.exe", "/c", "start", '""', f'"{chrome}"',
    f'--user-data-dir="{profile}"',
    '--profile-directory=Default',
    '--remote-debugging-port=9222',
    '--remote-allow-origins=*',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-sync',
    *NO_DISCARD_FLAGS,
    '--window-size=1400,900'
] + urls

full_cmd = " ".join(cmd)
print("Executing:", full_cmd)
os.system(full_cmd)

time.sleep(3)
for _ in range(5):
    try:
        raw = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3).read()
        print("[+] SUCCESS! Chrome CDP responding on port 9222:")
        print(raw.decode())
        break
    except Exception as e:
        print(f"Waiting for Chrome on 9222... ({e})")
        time.sleep(1)
