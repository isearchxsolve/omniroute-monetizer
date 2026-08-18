"""Inspect the accounts.google.com chooser page and click the account."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]

    g = None
    for pg in ctx.pages:
        if "accounts.google.com" in pg.url:
            g = pg
            break
    if g is None:
        print("no google page found")
        raise SystemExit

    g.bring_to_front()
    time.sleep(2)
    print("URL:", g.url[:120])
    print("TITLE:", g.title())

    # dump account entries
    info = g.evaluate("""() => {
        const out = [];
        // standard chooser rows
        document.querySelectorAll('[data-email], [data-identifier]').forEach(e => {
            out.push({tag: e.tagName, email: e.getAttribute('data-email')||e.getAttribute('data-identifier'), text:(e.innerText||'').replace(/\\n/g,' | ').slice(0,60)});
        });
        // any element mentioning the account
        document.querySelectorAll('div,li,button,a').forEach(e => {
            const t = (e.innerText||'');
            if (/xxpertcomments|Kunal/i.test(t) && t.length < 120) {
                out.push({tag: e.tagName, cls: (e.className||'').toString().slice(0,40), text: t.replace(/\\n/g,' | ').slice(0,80)});
            }
        });
        return out.slice(0, 25);
    }""")
    for i in info:
        print(i)
