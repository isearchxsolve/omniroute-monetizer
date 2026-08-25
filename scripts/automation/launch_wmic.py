import subprocess
import time
import urllib.request

cmd = r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="D:\omniroute-monetizer\state\automation_profiles\providers" --profile-directory=Default --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check --disable-sync --window-size=1400,900 https://arena.lmsys.org https://duckduckgo.com/ai https://huggingface.co/chat https://poe.com https://www.phind.com https://www.blackbox.ai'

print("Spawning via WMIC...")
wmic_cmd = f'wmic process call create \'{cmd}\''
res = subprocess.run(wmic_cmd, shell=True, capture_output=True, text=True)
print("WMIC Output:", res.stdout)

time.sleep(3)
for _ in range(5):
    try:
        raw = urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3).read()
        print("[+] SUCCESS! Persistent Chrome CDP responding on port 9222:")
        print(raw.decode())
        break
    except Exception as e:
        print(f"Waiting for 9222... ({e})")
        time.sleep(1)
