"""Dump all interactive controls (buttons/links) on an OmniRoute provider page.

Purpose: settle whether the "no reauth button" providers genuinely lack a
re-auth control, or whether it hides under different text / a menu.
Text-only friendly: prints button text + selector, no screenshots needed.
"""
import json
import sys
import requests
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:20128"
PASSWORD = "Keross@321"

# provider slug -> the page to open
SLUGS = sys.argv[1:] or ["xai-oauth", "codex", "antigravity", "kilocode"]


def login() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"password": PASSWORD}, timeout=10)
    r.raise_for_status()
    return s


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        # Log in through the actual sign-in form so the session cookie is set
        # in the browser context (cookie transfer from requests is unreliable).
        page.goto(f"{BASE_URL}/dashboard/providers", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(1500)
        try:
            pwd = page.locator('input[type="password"]').first
            pwd.wait_for(state="visible", timeout=5000)
            pwd.fill(PASSWORD)
            page.locator('button:has-text("Continue")').first.click(timeout=5000)
            page.wait_for_timeout(2500)
            print("[+] browser login submitted")
        except Exception as e:
            print(f"[!] browser login step skipped/failed: {e}")

        for slug in SLUGS:
            url = f"{BASE_URL}/dashboard/providers/{slug}"
            print("\n" + "=" * 72)
            print(f"PAGE: {url}")
            print("=" * 72)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"  !! navigation failed: {e}")
                continue

            # Dump every button / link / role=button with its visible text.
            controls = page.evaluate(
                """() => {
                    const out = [];
                    const els = Array.from(document.querySelectorAll(
                        'button, a, [role="button"], [role="menuitem"], [role="tab"]'
                    ));
                    for (const el of els) {
                        const text = (el.innerText || el.textContent || '').trim()
                            .replace(/\\s+/g, ' ').slice(0, 80);
                        const aria = el.getAttribute('aria-label') || '';
                        const title = el.getAttribute('title') || '';
                        const tag = el.tagName.toLowerCase();
                        const disabled = el.disabled || el.getAttribute('aria-disabled');
                        if (text || aria || title) {
                            out.push({tag, text, aria, title, disabled: !!disabled});
                        }
                    }
                    return out;
                }"""
            )
            print(f"  found {len(controls)} interactive controls:")
            for c in controls:
                flag = " [DISABLED]" if c["disabled"] else ""
                label = c["text"] or f"(aria:{c['aria']})" or f"(title:{c['title']})"
                print(f"    <{c['tag']}> {label}{flag}")

            # Also dump any element whose text mentions auth-ish keywords.
            auth_hits = page.evaluate(
                """() => {
                    const kw = /re-?auth|login|sign ?in|connect|import|refresh|link account|authorize/i;
                    const out = [];
                    const walker = document.createTreeWalker(
                        document.body, NodeFilter.SHOW_ELEMENT);
                    let n;
                    while ((n = walker.nextNode())) {
                        const t = (n.innerText || '').trim();
                        if (t && kw.test(t) && t.length < 60) {
                            out.push({tag: n.tagName.toLowerCase(), text: t.replace(/\\s+/g,' ')});
                        }
                    }
                    // dedupe
                    const seen = new Set();
                    return out.filter(x => {
                        const k = x.tag + '|' + x.text;
                        if (seen.has(k)) return false;
                        seen.add(k); return true;
                    }).slice(0, 40);
                }"""
            )
            print(f"  auth-keyword elements ({len(auth_hits)}):")
            for h in auth_hits:
                print(f"    <{h['tag']}> {h['text']}")

        browser.close()


if __name__ == "__main__":
    main()
