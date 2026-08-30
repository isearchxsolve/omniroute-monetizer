"""Launch the three offline Chrome profiles (niloy, seat2, seat3) on ports 9223-9225."""
import os, pathlib, subprocess, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_no_discard import NO_DISCARD_FLAGS

ROOT = pathlib.Path(r"D:\omniroute-monetizer")
PROFILES_DIR = ROOT / "state" / "automation_profiles"

SEATS = [
    (9223, "niloy"),
    (9224, "seat2"),
    (9225, "seat3"),
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

def launch(port, profile):
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
    print(f"[*] Launching {profile} on port {port}...")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    print(f"    PID: {proc.pid}")
    return proc

def wait_for_cdp(port, timeout=20):
    for i in range(timeout):
        time.sleep(1)
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2).read()
            print(f"[+] Port {port} CDP READY")
            return True
        except:
            pass
    print(f"[-] Port {port} CDP TIMEOUT")
    return False

procs = []
for port, profile in SEATS:
    p = launch(port, profile)
    procs.append((port, profile, p))

for port, profile, _ in procs:
    wait_for_cdp(port, 15)

print("\n[+] All three Chrome profiles launched.")
print("    9223 = niloy | 9224 = seat2 | 9225 = seat3")
