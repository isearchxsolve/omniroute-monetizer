"""CDP page helper: connect to the connected Chrome profile and run one navigation+inspection.
Usage: python cdp_page.py <url> [--text|--aria|--screenshot out.png]
Never prints secrets; only page structure/text."""
import sys
from playwright.sync_api import sync_playwright

def main():
    url = sys.argv[1] if len(sys.argv) > 1 else None
    mode = sys.argv[2] if len(sys.argv) > 2 else '--aria'
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
        ctx = browser.contexts[0]
        page = None
        # reuse an existing about:blank/newtab page if present
        for p in ctx.pages:
            if p.url in ('about:blank', 'chrome://newtab/'):
                page = p
                break
        if page is None:
            page = ctx.new_page()
        if url:
            page.goto(url, timeout=45000, wait_until='domcontentloaded')
            try:
                page.wait_for_load_state('load', timeout=15000)
            except Exception:
                pass
        print('URL:', page.url)
        print('TITLE:', page.title())
        if mode == '--text':
            body = page.evaluate('() => document.body ? document.body.innerText : ""')
            print('--- TEXT ---')
            print(body[:6000])
        elif mode == '--screenshot':
            out = sys.argv[3] if len(sys.argv) > 3 else 'scratch/shot.png'
            page.screenshot(path=out, full_page=False)
            print('screenshot ->', out)
        else:
            # aria snapshot (compact)
            try:
                snap = page.accessibility.snapshot(interesting_only=True)
                import json
                def walk(n, d=0):
                    if d > 6: return
                    name = (n.get('name') or '').strip()
                    role = n.get('role', '')
                    if name or role in ('button','link','textbox','combobox','checkbox','heading'):
                        print('  '*d + f"[{role}] {name[:110]}")
                    for c in n.get('children', []) or []:
                        walk(c, d+1)
                if snap:
                    walk(snap)
                else:
                    print('(no aria snapshot)')
            except Exception as e:
                print('aria error:', e)
        browser.close()

if __name__ == '__main__':
    main()
