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
