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
