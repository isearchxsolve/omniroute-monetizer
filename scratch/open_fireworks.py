#!/usr/bin/env python3
"""Open Fireworks AI signup page in the CDP Chrome and LEAVE IT OPEN.

Human-in-the-loop: user completes Google OAuth manually, then signals.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "automation"))

from signup_browser import ensure_chrome, attach  # noqa: E402

URL = "https://fireworks.ai/login"


def main():
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    with sync_playwright() as pw:
        browser = attach(pw)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.bring_to_front()
        print(f"[+] opened and focused: {page.url}")
        print("[+] tab left open — complete the login manually, then signal back.")


if __name__ == "__main__":
    main()
