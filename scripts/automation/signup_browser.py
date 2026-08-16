#!/usr/bin/env python3
"""Autonomous signup — browser layer (blueprint Module 0).

Ensures a plain (non-Playwright-launched) Chrome is running with the slim
profile copy and CDP on 127.0.0.1:9222, then attaches via Playwright CDP.

Why plain Chrome: Playwright-launched Chrome is unusably slow on this machine
(i5-3320M) and trips Google's headless/bot heuristics. Plain Chrome + CDP
attach is the proven pattern (see /memories/repo/browser_automation.md).

Read-only helpers here never print secrets (T11-safe).
"""
import json
import os
import socket
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE_DIR = r"d:\omniroute-chrome-profile"
PROFILE_NAME = "Profile 14"
CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"


def cdp_port_open() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", CDP_PORT)) == 0


def clear_crash_state() -> None:
    """Chrome refuses to restore a profile that thinks it crashed."""
    for prof in (PROFILE_NAME, "Profile", "Default"):
        prefs = os.path.join(PROFILE_DIR, prof, "Preferences")
        if not os.path.exists(prefs):
            continue
        try:
            with open(prefs, encoding="utf-8") as f:
                data = json.load(f)
            prof_section = data.setdefault("profile", {})
            prof_section["exit_type"] = "Normal"
            prof_section["exited_cleanly"] = True
            with open(prefs, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:  # noqa: BLE001
            print(f"[!] could not patch crash state in {prefs}: {e}")


def ensure_chrome() -> None:
    """Launch plain Chrome with CDP if not already listening."""
    if cdp_port_open():
        print(f"[*] CDP already listening on :{CDP_PORT}")
        return
    if not os.path.exists(CHROME_EXE):
        raise FileNotFoundError(f"Chrome not found at {CHROME_EXE}")
    if not os.path.isdir(os.path.join(PROFILE_DIR, PROFILE_NAME)):
        raise FileNotFoundError(f"Profile '{PROFILE_NAME}' missing in {PROFILE_DIR}")
    clear_crash_state()
    args = [
        CHROME_EXE,
        f"--user-data-dir={PROFILE_DIR}",
        f"--profile-directory={PROFILE_NAME}",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
    ]
    print(f"[*] launching plain Chrome with CDP on :{CDP_PORT} ...")
    subprocess.Popen(args)
    for _ in range(30):
        time.sleep(1)
        if cdp_port_open():
            print("[+] Chrome CDP is up")
            return
    raise RuntimeError(f"Chrome CDP did not come up on :{CDP_PORT} within 30s")


def attach(playwright):
    """Attach to the running Chrome over CDP. Caller owns the playwright ctx."""
    return playwright.chromium.connect_over_cdp(CDP_URL)


def new_page(browser, url: str = None):
    """Get a usable page: reuse an existing blank tab or open a new one."""
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = None
    for p in ctx.pages:
        if p.url in ("about:blank", "chrome://newtab/", "chrome://new-tab-page/"):
            page = p
            break
    if page is None:
        page = ctx.new_page()
    if url:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    return page


if __name__ == "__main__":
    ensure_chrome()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        br = attach(pw)
        pg = new_page(br, "https://example.com")
        print("[+] attached; test page title:", pg.title())
