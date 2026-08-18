"""Dump DOM of signin.t3.chat to find the actual Google sign-in button."""
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
    page = None
    for pg in ctx.pages:
        if "signin.t3.chat" in pg.url or "t3.chat" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()
        page.goto("https://t3.chat/auth/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

    print("URL:", page.url)
    # Dump all clickable elements with their tag, text, aria-label, and any google-related
    els = page.evaluate(
        """() => {
            const out = [];
            const els = Array.from(document.querySelectorAll('button, a, [role=button], [role=link], div[class*=btn], span'));
            for (const el of els) {
                const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
                if (!t) continue;
                const cls = (el.className || '').toString().slice(0, 60);
                out.push({tag: el.tagName, text: t.slice(0, 50), cls, href: el.getAttribute('href') || ''});
            }
            return out.slice(0, 80);
        }"""
    )
    for e in els:
        print(f"  <{e['tag']}> text={e['text']!r} cls={e['cls']!r} href={e['href'][:60]!r}")
    # Also dump any iframes
    print("\nframes:", [f.url[:80] for f in page.frames])
    browser.close()
