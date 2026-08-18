"""Recon app.blackbox.ai login page (the real auth surface)."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

PORT = 9223
KEYWORDS = ["google", "sign", "log", "get started", "continue", "start",
            "join", "account", "apple", "email", "sso", "oauth", "github"]


def dump(page, label):
    print(f"\n=== {label} -> final {page.url[:120]} ===")
    try:
        print(f"  title: {page.title()!r}")
    except Exception:
        pass
    els = page.evaluate(r"""() => {
        const out = [];
        const els = Array.from(document.querySelectorAll(
            'button, a, [role=button], [role=link], input[type=submit], div[onclick]'));
        for (const el of els) {
            const t = (el.innerText || el.value || '').trim().replace(/\s+/g, ' ');
            if (!t || t.length > 80) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 && r.height === 0) continue;
            out.push({tag: el.tagName, text: t,
                      cls: (el.className || '').toString().slice(0, 60),
                      href: (el.href || '').slice(0, 120)});
        }
        return out;
    }""")
    hits = [e for e in els
            if any(k in e["text"].lower() for k in KEYWORDS)
            or any(k in e["href"].lower() for k in ["auth", "login", "oauth", "google"])]
    print(f"  clickable elements: {len(els)}, auth-ish: {len(hits)}")
    for e in hits[:40]:
        print(f"  <{e['tag']}> text={e['text']!r} href={e['href']!r} cls={e['cls']!r}")
    if not hits:
        for e in els[:30]:
            print(f"  <{e['tag']}> text={e['text']!r} href={e['href']!r}")


with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=30000)
    ctx = browser.contexts[0]

    page = None
    for pg in ctx.pages:
        if "blackbox.ai" in pg.url:
            page = pg
            break
    if page is None:
        page = ctx.new_page()

    try:
        page.goto("https://app.blackbox.ai/login", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(6000)
    except Exception as e:
        print(f"goto err: {e}")
    dump(page, "app.blackbox.ai/login")

    browser.close()
