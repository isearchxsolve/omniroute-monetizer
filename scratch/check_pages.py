"""Check all open pages/popups after t3.chat Google click."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
PORT = 9223
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]
    print("=== all pages ===")
    for i, pg in enumerate(ctx.pages):
        try:
            print(f"  page {i}: {pg.url[:120]} | title={pg.title()[:50]!r}")
        except Exception as e:
            print(f"  page {i}: error {e}")
    # Check cookies for t3.chat
    print("\n=== t3.chat cookies ===")
    for c in ctx.cookies():
        dom = (c.get("domain") or "").lstrip(".").lower()
        if "t3.chat" in dom:
            print(f"  {c['name']:40s} len={len(c['value'])} httpOnly={c.get('httpOnly')}")
    browser.close()
