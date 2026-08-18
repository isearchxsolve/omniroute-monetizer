"""Meta.ai login flow: click Log in, then recon the auth options page."""
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 9223
KEYWORDS = ["google", "sign", "log", "continue", "facebook", "instagram",
            "whatsapp", "email", "account", "meta"]


def dump(page, label):
    print(f"\n=== {label} -> {page.url[:130]} ===")
    try:
        print(f"  title: {page.title()!r}")
    except Exception:
        pass
    els = page.evaluate(r"""() => {
        const out = [];
        const els = Array.from(document.querySelectorAll(
            'button, a, [role=button], [role=link], input[type=submit], div[onclick]'));
        for (const el of els) {
            const t = (el.innerText || el.value || el.getAttribute('aria-label') || '')
                .trim().replace(/\s+/g, ' ');
            if (!t || t.length > 90) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            out.push({tag: el.tagName, text: t,
                      cls: (el.className || '').toString().slice(0, 50),
                      href: (el.href || '').slice(0, 130)});
        }
        return out;
    }""")
    hits = [e for e in els
            if any(k in e["text"].lower() for k in KEYWORDS)
            or any(k in e["href"].lower() for k in ["auth", "login", "oauth", "google", "facebook"])]
    print(f"  elements: {len(els)}, auth-ish: {len(hits)}")
    for e in hits[:40]:
        print(f"  <{e['tag']}> text={e['text']!r} href={e['href']!r}")
    if not hits:
        for e in els[:30]:
            print(f"  <{e['tag']}> text={e['text']!r} href={e['href']!r}")


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    page = None
    for pg in ctx.pages:
        if "meta.ai" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()
        page.goto("https://www.meta.ai/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

    print(f"starting URL: {page.url[:120]}")

    # Click Log in
    clicked = False
    for sel in ["button:has-text('Log in')", "a:has-text('Log in')",
                "button:has-text('Sign up')"]:
        try:
            loc = page.locator(sel).first
            if loc.is_visible(timeout=4000):
                loc.click(timeout=6000)
                print(f"[click] {sel}")
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        print("!! no login button found")
        browser.close()
        sys.exit(1)

    page.wait_for_timeout(5000)

    # Dump current page + any new pages (popups)
    dump(page, "after login click")
    for pg in ctx.pages:
        if pg != page and ("facebook" in pg.url or "meta" in pg.url or "instagram" in pg.url):
            dump(pg, f"other page: {pg.url[:80]}")

    browser.close()
