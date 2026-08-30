"""Launch a single Chrome profile on a specific port."""
import os, pathlib, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_no_discard import NO_DISCARD_FLAGS

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
PROFILES_DIR = ROOT / "state" / "automation_profiles"

def find_chrome():
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        p = pathlib.Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
        if p.exists():
            return p
    raise SystemExit("Chrome not found")

port = int(sys.argv[1])
profile = sys.argv[2]
udd = PROFILES_DIR / profile
udd.mkdir(parents=True, exist_ok=True)
chrome = find_chrome()
flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
cmd = [
    str(chrome),
    f"--user-data-dir={udd}",
    f"--profile-directory=Default",
    f"--remote-debugging-port={port}",
    "--remote-allow-origins=*",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-sync",
    *NO_DISCARD_FLAGS,
    "--window-size=1400,900",
]
print(f"Launching {profile} on port {port}...")
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
print(f"PID: {proc.pid}")
for i in range(15):
    time.sleep(1)
    try:
        import urllib.request
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
        print(f"Port {port} CDP READY")
        sys.exit(0)
    except:
        pass
print(f"Port {port} CDP TIMEOUT")
