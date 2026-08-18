"""Autonomous Google SSO login driver for the PURE Chrome profile (CDP 9223).

The pure profile (Profile 14 = xxpertcomments@gmail.com) is ALREADY signed into
Google. So the automation drives each provider's "Continue with Google" flow and
Google AUTO-SELECTS the remembered account — no email/OTP, no bot detection, no
human step. This is the genuine autonomous login (gate relaxation #120).

Flow per provider:
  1. Navigate to the provider's login/sign-in page.
  2. Click the "Continue with Google" / "Sign in with Google" button.
  3. Wait for the Google accounts page; if an account is auto-selected, click
     "Continue"; otherwise click the remembered account.
  4. Wait for redirect back to the provider and for auth cookies to appear.
  5. Report which auth cookies are present (values NEVER printed — T11).

Usage: python scratch/autonomous_sso_login.py [provider...]
       (default: all of perplexity-web t3-web blackbox muse-spark-web)
"""
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KEYS_PATH = os.path.join(ROOT, "state", "generated_keys.json")
PORT = 9223

from playwright.sync_api import sync_playwright  # noqa: E402

# Provider -> (login URL, list of "Continue with Google" button selectors)
PROVIDERS = {
    "perplexity-web": {
        "login_url": "https://www.perplexity.ai/settings/account",
        "google_btn": [
            "button:has-text('Continue with Google')",
            "button:has-text('Sign in with Google')",
            "a:has-text('Continue with Google')",
            "a:has-text('Sign in with Google')",
            "button:has-text('Google')",
        ],
        "auth_cookies": ["__Secure-next-auth.session-token", "__Secure-perplexity_session"],
        "signed_in_marker": ["text=Log out", "text=Sign out", "text=Account"],
    },
    "t3-web": {
        "login_url": "https://t3.chat",
        "google_btn": [
            "button:has-text('Continue with Google')",
            "button:has-text('Sign in with Google')",
            "a:has-text('Continue with Google')",
            "a:has-text('Sign in with Google')",
            "button:has-text('Google')",
        ],
        "auth_cookies": ["convex-session-id", "sessionToken"],
        "signed_in_marker": ["text=Log out", "text=Sign out"],
    },
    "blackbox": {
        "login_url": "https://www.blackbox.ai/login",
        "google_btn": [
            "button:has-text('Continue with Google')",
            "button:has-text('Sign in with Google')",
            "a:has-text('Continue with Google')",
            "a:has-text('Sign in with Google')",
            "button:has-text('Google')",
        ],
        "auth_cookies": ["token", "session", "auth"],
        "signed_in_marker": ["text=Log out", "text=Sign out"],
    },
    "muse-spark-web": {
        "login_url": "https://www.meta.ai",
        "google_btn": [
            "button:has-text('Continue with Google')",
            "button:has-text('Sign in with Google')",
            "a:has-text('Continue with Google')",
            "a:has-text('Sign in with Google')",
            "button:has-text('Google')",
        ],
        "auth_cookies": ["c_user", "xs", "sessionid"],
        "signed_in_marker": ["text=Log out", "text=Sign out"],
    },
}


def get_cookies(ctx):
    try:
        return ctx.cookies()
    except Exception:
        return []


def cookie_names_for(ctx, domain_hint):
    names = set()
    for c in get_cookies(ctx):
        dom = (c.get("domain") or "").lstrip(".").lower()
        if domain_hint in dom or dom.endswith(domain_hint):
            names.add(c["name"])
    return names


def try_click(page, selectors, timeout=8000):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=timeout):
                loc.click(timeout=timeout)
                print(f"    clicked: {sel}")
                return True
        except Exception:
            continue
    return False


def handle_google_accounts(page, timeout=15000):
    """On accounts.google.com, click the remembered account or Continue."""
    # Wait for accounts.google.com to load
    try:
        page.wait_for_url("**accounts.google.com**", timeout=timeout)
    except Exception:
        pass
    time.sleep(2)
    # If an account is auto-selected, there's a "Continue" button
    for sel in ["button:has-text('Continue')", "button:has-text('Continue as')",
                "div[role=link]:has-text('xxpertcomments')",
                "div[data-email*='gmail.com']"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print(f"    google: clicked {sel}")
                return True
        except Exception:
            continue
    return False


def login_provider(p, ctx, slug, cfg):
    print(f"\n=== {slug} ===")
    page = ctx.new_page()
    try:
        page.goto(cfg["login_url"], wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)
        print(f"  loaded {cfg['login_url']} title={page.title()[:60]!r}")

        # If already signed in, skip
        names = cookie_names_for(ctx, slug.split("-")[0])
        present = [c for c in cfg["auth_cookies"] if c in names]
        if present:
            print(f"  already signed in (auth cookies present: {present})")
            page.close()
            return "already"

        # Click Continue with Google
        if not try_click(page, cfg["google_btn"]):
            print("  !! no 'Continue with Google' button found — page may differ")
            page.close()
            return "no_button"

        # Handle Google accounts page
        handle_google_accounts(page)

        # Wait for redirect back + auth cookies
        deadline = time.time() + 45
        while time.time() < deadline:
            time.sleep(3)
            names = cookie_names_for(ctx, slug.split("-")[0])
            present = [c for c in cfg["auth_cookies"] if c in names]
            if present:
                print(f"  SIGNED IN — auth cookies present: {present}")
                page.close()
                return "signed_in"
        print("  timeout waiting for auth cookies")
        page.close()
        return "timeout"
    except Exception as e:
        print(f"  ERROR: {e}")
        try:
            page.close()
        except Exception:
            pass
        return "error"


def main():
    args = sys.argv[1:]
    targets = args if args else list(PROVIDERS.keys())
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
        ctx = browser.contexts[0]
        for slug in targets:
            if slug not in PROVIDERS:
                print(f"unknown provider {slug}")
                continue
            results[slug] = login_provider(p, ctx, slug, PROVIDERS[slug])
        browser.close()
    print("\n=== SUMMARY ===")
    for slug, res in results.items():
        print(f"  {slug:20s} -> {res}")


if __name__ == "__main__":
    main()
