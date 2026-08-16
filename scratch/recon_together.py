#!/usr/bin/env python3
"""Recon: Together AI signup/login page via logged-in Chrome CDP.

Read-only. Dumps page state to find the Google OAuth button and post-login
API-key page structure. T11-safe (no secrets printed).
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "automation"))

from signup_browser import ensure_chrome, attach  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RECON_DIR = os.path.join(ROOT, "state", "dom_recon")
os.makedirs(RECON_DIR, exist_ok=True)

URLS = {
    "signup": "https://api.together.ai/signin",
    "home": "https://www.together.ai/",
    "apikeys": "https://api.together.ai/settings/api-keys",
}


def dump(page, tag):
    state = {"tag": tag, "url": page.url, "title": ""}
    try:
        state["title"] = page.title()
        state["buttons"] = page.evaluate(
            """() => Array.from(document.querySelectorAll('button, a, [role=button]'))
                .map(b => (b.innerText || b.getAttribute('aria-label') || '').trim())
                .filter(t => t && t.length < 90).slice(0, 60)"""
        )
        state["body_sample"] = page.evaluate("() => document.body.innerText.slice(0, 1500)")
    except Exception as e:
        state["err"] = str(e)[:150]
    path = os.path.join(RECON_DIR, f"together_{tag}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"[*] {tag}: url={state['url'][:80]} title={state.get('title','')!r}")
    print(f"    buttons={state.get('buttons', [])[:30]}")
    print(f"    body[:250]={state.get('body_sample','')[:250]!r}")
    return state


def main():
    ensure_chrome()
    from playwright.sync_api import sync_playwright  # noqa: E402

    with sync_playwright() as pw:
        browser = attach(pw)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(URLS["signup"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
            dump(page, "signin")
        except Exception as e:
            print("[-] signin nav failed:", str(e)[:150])
        finally:
            try:
                page.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
