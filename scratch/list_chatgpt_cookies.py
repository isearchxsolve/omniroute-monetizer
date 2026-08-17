#!/usr/bin/env python3
"""List all cookie NAMES on chatgpt.com / openai.com domains (values redacted)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=30000)
    ctx = browser.contexts[0]
    cookies = ctx.cookies()
    browser.close()

for c in cookies:
    d = (c.get("domain") or "").lower()
    if "chatgpt" in d or "openai" in d:
        v = c.get("value") or ""
        print(f"  {d:28s} {c.get('name'):40s} len={len(v):5d} "
              f"secure={c.get('secure')} httpOnly={c.get('httpOnly')}")
