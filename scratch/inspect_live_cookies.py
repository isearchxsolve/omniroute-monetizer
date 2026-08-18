"""Inspect live cookies for t3.chat / blackbox.ai / meta.ai to determine real auth state."""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
PORT = 9223
from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]
    cookies = ctx.cookies()
    browser.close()

for target in ["t3.chat", "blackbox.ai", "meta.ai", "perplexity.ai"]:
    print(f"\n=== {target} ===")
    for c in cookies:
        dom = (c.get("domain") or "").lstrip(".").lower()
        if target in dom:
            print(f"  {c['name']:45s} len={len(c['value'])} httpOnly={c.get('httpOnly')}")
