"""chat_seat_daemon.py — Long-running seat daemon that keeps Chrome open with candidate chat tabs on port 9222.
"""
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
STATE = ROOT / "state"
PROFILES_DIR = STATE / "automation_profiles"
SECRETS_DIR = STATE / "secrets"

PORT = 9222
PROFILE = "providers"
SUBPROFILE = "Default"

TARGET_URLS = [
    "https://arena.lmsys.org",
    "https://duckduckgo.com/ai",
    "https://huggingface.co/chat",
    "https://poe.com",
    "https://www.phind.com",
    "https://www.blackbox.ai",
    "https://www.perplexity.ai",
    "https://v0.dev",
    "https://puter.com"
]

def find_chrome():
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        p = pathlib.Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if p.exists():
            return p
    raise SystemExit("Chrome not found")

def main():
    udd = PROFILES_DIR / PROFILE
    udd.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome()

    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200

    cmd = [
        str(chrome),
        f"--user-data-dir={udd}",
        f"--profile-directory={SUBPROFILE}",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--window-size=1400,900"
    ] + TARGET_URLS

    print(f"[*] Starting Chrome Seat Daemon on port {PORT}...")
    print(f"[*] Profile: {udd} ({SUBPROFILE})")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True
    )

    print(f"[+] Chrome PID: {proc.pid}")

    # Verify CDP is responsive
    for _ in range(15):
        time.sleep(1)
        try:
            raw = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2).read()
            print(f"[+] SUCCESS! Chrome CDP responding on port {PORT}")
            break
        except Exception:
            pass

    # Keep daemon alive to anchor the child process
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("[*] Shutting down seat daemon...")
        proc.terminate()

if __name__ == "__main__":
    main()
