"""Inspect current tabs in Robot Chrome and handle whatever is on screen.
"""
from __future__ import annotations
import pathlib
import sys
import time
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from chrome_live_guard import assert_safe, safe_profile_dir
from provider_login_helper import ROBOT_CDP_PORT

SHOTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "state" / "harvest" / "pilot_shots"

def inspect():
    udd = safe_profile_dir("providers")
    assert_safe(udd, who="cdp_pilot")
    
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{ROBOT_CDP_PORT}")
        ctx = browser.contexts[0]
        print(f"[+] Context pages: {len(ctx.pages)}")
        for idx, p in enumerate(ctx.pages):
            p.bring_to_front()
            print(f"--- Page {idx} ---")
            print(f"URL: {p.url}")
            print(f"Title: {p.title()}")
            shot_file = SHOTS_DIR / f"tab_{idx}.png"
            p.screenshot(path=str(shot_file))
            print(f"Screenshot: {shot_file}")
            body = p.inner_text("body")
            print(f"Body: {body[:400].replace(chr(10), ' ')}")

if __name__ == "__main__":
    inspect()
