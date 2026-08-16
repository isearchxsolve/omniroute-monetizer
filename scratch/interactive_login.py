#!/usr/bin/env python3
"""Interactive session refresher — RUN THIS IN YOUR OWN TERMINAL (Session 1).

Opens a VISIBLE Chromium window using the persistent profile at
state/browser_profile and walks through the 3 provider login pages.
You complete each login manually (Google/Apple/SSO/MFA — whatever is needed).
Press Enter in the terminal after finishing each site; the script saves the
refreshed storage_state.json when done.

Per AGENTS.md anti-pattern #8: background IDE agents run in Session 0 and their
browser windows are invisible — this MUST be run by you in your own cmd/PowerShell.

Usage:
    cd d:\\omniroute-monetizer
    .\\.venv\\Scripts\\python.exe -u scratch\\interactive_login.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROFILE = os.path.join(ROOT, "state", "browser_profile")
STATE = os.path.join(PROFILE, "storage_state.json")

# Chrome REFUSES remote debugging on its default User Data dir (security restriction),
# so we automate a COPY of the real profile (cookies/logins included; DPAPI still works
# for the same Windows user). Copy made via robocopy (caches excluded).
CHROME_USER_DATA = r"d:\omniroute-chrome-profile"
CHROME_PROFILE_DIR = "Profile 14"  # "Person 1"


def _clear_crash_state():
    """Force-killed profiles are marked ExitType=Crashed -> restore bubble stalls automation."""
    import json as _json
    prefs = os.path.join(CHROME_USER_DATA, CHROME_PROFILE_DIR, "Preferences")
    try:
        with open(prefs, encoding="utf-8") as f:
            data = _json.load(f)
        prof = data.setdefault("profile", {})
        if prof.get("exit_type") != "Normal":
            prof["exit_type"] = "Normal"
            prof["exited_cleanly"] = True
            with open(prefs, "w", encoding="utf-8") as f:
                _json.dump(data, f, separators=(",", ":"))
            print("[*] Cleared crash state in copied profile Preferences")
    except Exception as e:
        print(f"[!] Could not clear crash state: {type(e).__name__}: {e}")

SITES = [
    ("OpenRouter", "https://openrouter.ai/sign-in"),
    ("Anthropic", "https://console.anthropic.com/settings/keys"),
    ("GitHub", "https://github.com/login"),
]


def main():
    print("=" * 60)
    print("INTERACTIVE LOGIN REFRESHER (visible browser window)")
    print("Complete each login in the browser, then press Enter here.")
    print("=" * 60)
    _clear_crash_state()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            CHROME_USER_DATA,
            channel="chrome",  # real installed Chrome, not Playwright's Chromium
            headless=False,
            args=[
                f"--profile-directory={CHROME_PROFILE_DIR}",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--hide-crash-restore-bubble",
            ],
            viewport={"width": 1280, "height": 900},
            timeout=120000,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for name, url in SITES:
            print(f"\n>>> Opening {name}: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"    (navigation note: {type(e).__name__})")
            ans = input(f"    [Press Enter when you have finished logging in to {name}, "
                        f"or type 'skip' to skip] > ").strip().lower()
            if ans == "skip":
                print(f"    (skipped {name})")
        ctx.storage_state(path=STATE)
        print(f"\n[OK] storage_state.json saved: {STATE}")
        ctx.close()
    print("Done. The DOM adapters can now run autonomously against fresh sessions.")


if __name__ == "__main__":
    main()
