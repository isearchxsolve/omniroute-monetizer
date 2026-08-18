"""Click login entry for yuanbao, codebuddy, zed; inspect what auth options appear."""
import time
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"

def dump(page, label):
    print(f"--- {label} ---")
    print("URL:", page.url[:130])
    info = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('button,a,[role=button],img[alt]').forEach(e => {
            const t = ((e.innerText||e.alt||'')+'').trim();
            if (t && t.length < 60) out.push({tag: e.tagName, text: t.replace(/\\n/g,' ').slice(0,55), href:(e.href||'').slice(0,80)});
        });
        return out.slice(0, 30);
    }""")
    for i in info:
        print("  ", i)
    body = page.evaluate("() => document.body ? document.body.innerText.slice(0,250) : ''")
    print("BODY:", repr(body[:200]))

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    # ---- yuanbao ----
    print("\n===== yuanbao-web =====")
    page = ctx.new_page()
    try:
        page.goto("https://yuanbao.tencent.com/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        try:
            page.locator("button:has-text('Log In')").first.click(timeout=6000)
            print("clicked Log In")
        except Exception as e:
            print("click fail:", str(e)[:80])
        time.sleep(5)
        dump(page, "yuanbao after click")
        # check for popup pages
        for pg in ctx.pages:
            if pg != page and ("yuanbao" in pg.url or "tencent" in pg.url or "x5" in pg.url):
                dump(pg, "yuanbao popup")
    finally:
        page.close()

    # ---- codebuddy ----
    print("\n===== codebuddy-cn =====")
    page = ctx.new_page()
    try:
        page.goto("https://copilot.tencent.com", wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        try:
            page.locator("button:has-text('登录')").first.click(timeout=6000)
            print("clicked 登录")
        except Exception as e:
            print("click fail:", str(e)[:80])
        time.sleep(5)
        dump(page, "codebuddy after click")
        for pg in ctx.pages:
            if pg != page and ("tencent" in pg.url or "codebuddy" in pg.url):
                dump(pg, "codebuddy popup")
    finally:
        page.close()

    # ---- zed ----
    print("\n===== zed-hosted =====")
    page = ctx.new_page()
    try:
        page.goto("https://zed.dev/sign_in", wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        dump(page, "zed sign_in")
    finally:
        page.close()
