import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = b.contexts[0]
        page = None
        for pg in ctx.pages:
            if "huggingface.co/join" in pg.url:
                page = pg
                break
        if not page:
            print("no /join tab")
            return
        info = await page.evaluate("""() => {
            const out = {iframes: [], hcaptchaVisible: false, bodyText: '', alerts: [], successHints: []};
            for (const f of document.querySelectorAll('iframe')) {
                const r = f.getBoundingClientRect();
                const style = getComputedStyle(f);
                out.iframes.push({src: (f.src||'').slice(0,120), w: r.width, h: r.height, display: style.display, visibility: style.visibility});
                if ((f.src||'').includes('hcaptcha') && r.width > 0 && r.height > 0 && style.display !== 'none') out.hcaptchaVisible = true;
            }
            // look for the hcaptcha container / checkbox
            const hc = document.querySelector('[data-hcaptcha], .hcaptcha, iframe[src*="hcaptcha"]');
            if (hc) {
                const r = hc.getBoundingClientRect();
                out.hcaptchaBox = {w: r.width, h: r.height};
            }
            for (const a of document.querySelectorAll('[role="alert"], .alert, .error, [class*="error"]')) {
                const t = (a.innerText||'').trim();
                if (t) out.alerts.push(t.slice(0,200));
            }
            const body = document.body.innerText || '';
            out.bodyText = body.slice(0, 600);
            for (const kw of ['Verify', 'verify', 'captcha', 'Captcha', 'success', 'Welcome', 'Check your email', 'created']) {
                if (body.includes(kw)) out.successHints.push(kw);
            }
            return out;
        }""")
        print(json.dumps(info, indent=2))

asyncio.run(main())
