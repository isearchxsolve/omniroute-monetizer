"""DOM recon for Perplexity: dump all clickable/interactive elements with auth-ish text.

Checks the currently-open perplexity page(s) AND perplexity.ai home, listing every
button/link whose text hints at login/signup/get-started/Google so we can pick
the right entry point for the click-through.
"""
import sys

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

JS_DUMP = r"""() => {
    const out = [];
    const els = Array.from(document.querySelectorAll('button, a, [role=button], [role=link], [role=menuitem], div[onclick], span[onclick]'));
    for (const el of els) {
        const t = (el.innerText || el.getAttribute('aria-label') || el.value || '').trim().replace(/\s+/g, ' ');
        if (!t || t.length > 80) continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        out.push({
            tag: el.tagName,
            text: t,
            cls: (el.className && el.className.toString().slice(0, 60)) || '',
            href: (el.getAttribute && el.getAttribute('href') || '').slice(0, 80),
        });
    }
    return out;
}"""

KEYWORDS = ["google", "sign", "log", "get started", "continue", "start", "join",
            "account", "apple", "email", "sso", "oauth"]

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=30000)
    ctx = browser.contexts[0]

    # Find existing perplexity pages
    pplx_pages = [pg for pg in ctx.pages if "perplexity.ai" in pg.url]
    print(f"existing perplexity pages: {len(pplx_pages)}")
    for pg in pplx_pages:
        print(f"  URL: {pg.url[:150]}")
        try:
            items = pg.evaluate(JS_DUMP)
            hits = [i for i in items if any(k in i["text"].lower() for k in KEYWORDS)]
            print(f"  auth-ish elements ({len(hits)}):")
            for i in hits[:30]:
                print(f"    <{i['tag']}> text={i['text']!r} href={i['href']!r} cls={i['cls']!r}")
            if not hits:
                print(f"  (no auth-ish; total elements: {len(items)})")
                for i in items[:15]:
                    print(f"    <{i['tag']}> text={i['text']!r}")
        except Exception as e:
            print(f"  eval err: {e}")

    # Also load fresh home + settings/account in a new page to see logged-out state
    page = ctx.new_page()
    for url in ["https://www.perplexity.ai/", "https://www.perplexity.ai/settings/account"]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)
            print(f"\n=== {url} -> final {page.url[:120]} ===")
            print(f"  title: {page.title()[:80]!r}")
            items = page.evaluate(JS_DUMP)
            hits = [i for i in items if any(k in i["text"].lower() for k in KEYWORDS)]
            print(f"  auth-ish elements ({len(hits)}):")
            for i in hits[:30]:
                print(f"    <{i['tag']}> text={i['text']!r} href={i['href']!r}")
        except Exception as e:
            print(f"  goto err: {e}")
    page.close()
    browser.close()
