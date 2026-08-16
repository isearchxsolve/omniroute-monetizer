#!/usr/bin/env python3
"""Export fresh sessions from the user's logged-in Chrome (CDP on :9222) to
state/browser_profile/storage_state.json. No navigation, no clicks — pure export.
T11: cookie values are never printed."""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "state", "browser_profile", "storage_state.json")

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=30000)
    ctx = browser.contexts[0]
    state = ctx.storage_state(path=OUT)
    cookies = state.get("cookies", [])
    origins = state.get("origins", [])
    print(f"exported {len(cookies)} cookies, {len(origins)} localStorage origins -> {OUT}")
    # per-domain cookie NAME summary only (values redacted)
    domains = {}
    for c in cookies:
        domains.setdefault(c.get("domain", "?"), []).append(c.get("name", "?"))
    for d in sorted(domains):
        if any(k in d for k in ("openrouter", "anthropic", "claude", "github")):
            print(f"  {d}: {len(domains[d])} cookies: {sorted(set(domains[d]))[:10]}")
    browser.close()
print("DONE")
