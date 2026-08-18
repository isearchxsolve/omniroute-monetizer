"""Autonomous Google SSO click-through driver for the PURE Chrome profile (CDP 9223).

Modeled on the PROVEN HuggingFace/Gemini baseline: the automation performs REAL
clicks on the provider's Google sign-in button, handles the Google account
chooser to auto-select the remembered account (xxpertcomments@gmail.com), and
completes the login. The pure profile is already signed into Google, so no
email/OTP, no bot detection, no human step.

The whole point is the AUTOMATION does the clicking. We ALWAYS attempt the real
click-through and only report success when a STRONG auth cookie appears after
the flow (weak/anonymous cookies like convex-session-id, datr, rd_challenge are
NOT proof of login).

Usage: python scratch/autonomous_sso_login.py [provider...]
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
        "strong_cookies": ["__Secure-next-auth.session-token", "__Secure-perplexity_session"],
        "domain": "perplexity.ai",
    },
    "t3-web": {
        "login_url": "https://t3.chat/auth/login",
        "google_btn": [
            "a:has-text('Continue with Google')",
            "button:has-text('Continue with Google')",
            "a:has-text('Sign in with Google')",
            "button:has-text('Sign in with Google')",
            "a:has-text('Google')",
            "button:has-text('Google')",
        ],
        "strong_cookies": ["session", "access-token", "sessionToken", "t3-session", "authjs.session-token"],
        "domain": "t3.chat",
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
        "strong_cookies": ["token", "session", "auth", "jwt"],
        "domain": "blackbox.ai",
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
        "strong_cookies": ["c_user", "xs", "sessionid"],
        "domain": "meta.ai",
    },
}


def get_cookies(ctx):
    try:
        return ctx.cookies()
    except Exception:
        return []


def strong_cookies_present(ctx, cfg):
    names = set()
    for c in get_cookies(ctx):
        dom = (c.get("domain") or "").lstrip(".").lower()
        if cfg["domain"] in dom or dom.endswith(cfg["domain"]):
            names.add(c["name"])
    return [c for c in cfg["strong_cookies"] if c in names]


def click_google_button(page, cfg):
    """REAL click on the provider's Google sign-in button (button OR anchor)."""
    for sel in cfg["google_btn"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=4000):
                loc.click(timeout=6000)
                print(f"    [click] Google button: {sel}")
                return True
        except Exception:
            continue
    # Fallback: any element whose text mentions Google + sign/continue/log
    try:
        clicked = page.evaluate(
            r"""() => {
                const els = Array.from(document.querySelectorAll('button, a, [role=button], [role=link]'));
                for (const el of els) {
                    const t = (el.innerText || el.getAttribute('aria-label') || '').trim();
                    if (/google/i.test(t) && /(sign|continue|log|in|up)/i.test(t)) {
                        el.click(); return t.slice(0, 60);
                    }
                }
                return null;
            }"""
        )
        if clicked:
            print(f"    [click] Google button (fallback): {clicked!r}")
            return True
    except Exception:
        pass
    return False


def handle_google_account_chooser(page):
    """On accounts.google.com, auto-select the remembered account."""
    if "accounts.google.com" not in page.url:
        return False
    print("    [google] account chooser detected; selecting remembered account ...")
    picked = page.evaluate(
        r"""() => {
            const els = Array.from(document.querySelectorAll('[data-email], [data-identifier], li, button, a, div[role=link]'));
            for (const el of els) {
                const email = el.getAttribute && (el.getAttribute('data-email') || el.getAttribute('data-identifier'));
                if (email && /@/.test(email)) { el.click(); return email; }
            }
            for (const el of els) {
                const t = (el.innerText || '').trim();
                const m = t.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
                if (m) { el.click(); return m[0]; }
            }
            for (const el of els) {
                const t = (el.innerText || '').trim();
                if (/^continue$/i.test(t)) { el.click(); return 'Continue'; }
            }
            return null;
        }"""
    )
    if picked:
        print(f"    [google] clicked: {picked}")
        page.wait_for_timeout(4000)
        return True
    print("    [google] no account element found")
    return False


def handle_google_consent(page):
    """On the Google consent page, click Continue/Allow."""
    if "accounts.google.com" not in page.url:
        return False
    for sel in ["button:has-text('Continue')", "button:has-text('Allow')",
                "button:has-text('Continue as')"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=3000):
                loc.click(timeout=5000)
                print(f"    [google] consent clicked: {sel}")
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

        # ALWAYS attempt the real click-through (the whole point of automation).
        if not click_google_button(page, cfg):
            print("  !! no Google sign-in button found on this page")
            # Try to find a login/sign-in link first
            found_login = False
            for sel in ["a:has-text('Sign in')", "a:has-text('Log in')",
                        "button:has-text('Sign in')", "button:has-text('Log in')",
                        "a:has-text('Login')"]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=3000):
                        loc.click(timeout=5000)
                        print(f"    [click] login link: {sel}")
                        time.sleep(3)
                        found_login = True
                        if click_google_button(page, cfg):
                            break
                except Exception:
                    continue
            if not found_login:
                page.close()
                return "no_google_button"

        # Handle Google account chooser + consent across all pages (incl. popups)
        deadline = time.time() + 90
        while time.time() < deadline:
            time.sleep(3)
            # Check all pages for Google account chooser / consent
            for pg in ctx.pages:
                if "accounts.google.com" in pg.url:
                    if handle_google_account_chooser(pg):
                        pg.wait_for_timeout(3000)
                    if handle_google_consent(pg):
                        pg.wait_for_timeout(3000)
            # Check for strong auth cookie
            present = strong_cookies_present(ctx, cfg)
            if present:
                print(f"  [OK] SIGNED IN — strong auth cookies: {present}")
                page.close()
                return "signed_in"
        print("  timeout waiting for strong auth cookie after click-through")
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
