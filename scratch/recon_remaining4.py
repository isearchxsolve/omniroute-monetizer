"""DOM recon: find login entry buttons for adapta-web, yuanbao-web, codebuddy-cn, zed-hosted."""
import time
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"

TARGETS = {
    "adapta-web": "https://agent.adapta.one",
    "yuanbao-web": "https://yuanbao.tencent.com",
    "codebuddy-cn": "https://copilot.tencent.com",
    "zed-hosted": "https://zed.dev",
}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    for slug, url in TARGETS.items():
        print(f"\n===== {slug} -> {url} =====")
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(5)
            print("final URL:", page.url[:120])
            print("TITLE:", page.title()[:80])

            # dump buttons/links that look like login entries
            info = page.evaluate("""() => {
                const out = [];
                document.querySelectorAll('button,a,[role=button]').forEach(e => {
                    const t = (e.innerText||'').trim();
                    if (t && t.length < 50 && /sign|log|login|google|start|account|continue|get started|注册|登录|微信|qq/i.test(t)) {
                        out.push({tag: e.tagName, text: t.replace(/\\n/g,' ').slice(0,45), href: (e.href||'').slice(0,70)});
                    }
                });
                return out.slice(0, 20);
            }""")
            for i in info:
                print("  ", i)

            body = page.evaluate("() => document.body ? document.body.innerText.slice(0,200) : ''")
            print("BODY:", repr(body[:150]))
        except Exception as e:
            print("ERROR:", type(e).__name__, str(e)[:120])
        finally:
            page.close()
