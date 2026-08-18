"""Launch a PURE Chrome profile for user-driven Google SSO signups (gate relaxation #120).

Pure = a copy of the user's REAL Chrome Profile 14 (Google already signed in,
provider logins present) with ALL extensions stripped (the VPN extension is what
tripped hCaptcha before) and heavy caches removed. NOT a blank profile — a blank
profile has no Google identity and would force email/password + OTP, defeating
the purpose. Real Chrome fingerprint + existing Google session = no bot detection,
no email OTP; the user's one-click account selection is the only human step.
Nothing is automated. CDP on port 9223 (slim profile uses 9222) so harvest can
attach afterwards. Stdlib only.

RCA (worklog #121): first attempt used a brand-new empty user-data-dir = blank
profile (no Accounts folder, no account_info) -> wrong. Fixed by copying the
real-login profile and purifying it.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = r"d:\omniroute-pure-chrome"
PROFILE_DIR = "Profile 14"   # the real-login profile (Google signed in), extensions stripped
PORT = 9223

# Wave-1 Google-SSO candidates: open their sign-in pages directly.
STARTUP_TABS = [
    "https://www.perplexity.ai/settings/account",   # perplexity-web
    "https://t3.chat",                              # t3-web
    "https://www.blackbox.ai/login",                # blackbox
    "https://www.meta.ai",                          # muse-spark-web
]


def cdp_up():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=5) as r:
            return json.loads(r.read()).get("Browser", "?")
    except Exception:
        return None


def main():
    ver = cdp_up()
    if ver:
        print(f"CDP already up on {PORT}: {ver}")
        print("Open the tabs manually if needed; harvest with scratch/harvest_pure_chrome.py")
        return

    os.makedirs(PROFILE, exist_ok=True)

    args = [
        CHROME,
        f"--user-data-dir={PROFILE}",
        f"--profile-directory={PROFILE_DIR}",
        f"--remote-debugging-port={PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",          # pure profile: nothing installed
        "--restore-last-session=false",
    ] + STARTUP_TABS

    subprocess.Popen(args)
    print("Pure Chrome launching (fresh profile, no extensions)...")
    for i in range(30):
        time.sleep(2)
        ver = cdp_up()
        if ver:
            print(f"CDP up on {PORT} after ~{(i+1)*2}s: {ver}")
            print()
            print("Tabs opened:")
            for t in STARTUP_TABS:
                print(f"  - {t}")
            print()
            print("NEXT: in each tab, click 'Continue with Google' and pick your account.")
            print("When done, run: python scratch/harvest_pure_chrome.py")
            return
    print("CDP still down after 60s — check Chrome manually.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
