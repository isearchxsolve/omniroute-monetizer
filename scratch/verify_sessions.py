#!/usr/bin/env python3
"""Verify the freshly exported storage_state.json actually authenticates on all 3
dashboards (headless, read-only, no clicks)."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
STATE = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")

TARGETS = [
    ("openrouter", "https://openrouter.ai/keys",
     ["sign in", "sign-in"], ["create key", "api key", "keys"]),
    ("anthropic", "https://console.anthropic.com/settings/keys",
     ["sign in", "log in", "continue with"], ["create key", "api keys"]),
    ("github", "https://github.com/settings/tokens",
     ["sign in to github", "username or email"], ["personal access tokens", "generate new token"]),
]

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=STATE, viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    for name, url, login_markers, authed_markers in TARGETS:
        entry = {"name": name, "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            entry["http_status"] = resp.status if resp else None
            page.wait_for_timeout(4000)
            entry["final_url"] = page.url
            body = (page.evaluate("() => (document.body && document.body.innerText) || ''") or "")[:2000].lower()
            title = (page.title() or "").lower()
            hay = body + " " + title
            login_hit = [m for m in login_markers if m in hay]
            authed_hit = [m for m in authed_markers if m in hay]
            if authed_hit and not login_hit:
                v = "AUTHENTICATED"
            elif login_hit and not authed_hit:
                v = "AUTH_WALL"
            elif authed_hit and login_hit:
                v = "AMBIGUOUS"
            else:
                v = "UNKNOWN"
            entry["verdict"] = v
            entry["login_hits"] = login_hit
            entry["authed_hits"] = authed_hit
            print(f"{name}: {v}  final_url={entry['final_url'][:90]}")
            print(f"   login_hits={login_hit} authed_hits={authed_hit}")
        except Exception as e:
            entry["verdict"] = "ERROR"
            entry["error"] = f"{type(e).__name__}: {str(e)[:150]}"
            print(f"{name}: ERROR {entry['error']}")
        results.append(entry)
    browser.close()

out = os.path.join(ROOT, "state", "dom_recon", "session_verify.json")
json.dump(results, open(out, "w", encoding="utf-8"), indent=2)
print(f"\nsaved -> {out}")
