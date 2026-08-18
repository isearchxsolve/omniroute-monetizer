"""Focused recon: zed sign_in content; yuanbao/codebuddy login modal (QR/WeChat)."""
import time
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"

def dump(page, label):
    print(f"--- {label} ---")
    try:
        print("URL:", page.url[:130])
        info = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('button,a,[role=button],img[alt],canvas,svg').forEach(e => {
                const t = ((e.innerText||e.alt||'')+'').trim();
                const tag = e.tagName;
                if ((t && t.length < 60) || tag==='CANVAS' || (tag==='IMG' && /qr|wechat|weixin|qq|google/i.test((e.src||'')+(e.alt||'')))) {
                    out.push({tag, text: t.replace(/\\n/g,' ').slice(0,50), href:(e.href||'').slice(0,80), src:(e.src||'').slice(0,60)});
                }
            });
            return out.slice(0, 30);
        }""")
        for i in info:
            print("  ", i)
        body = page.evaluate("() => document.body ? document.body.innerText.slice(0,300) : ''")
        print("BODY:", repr(body[:250]))
    except Exception as e:
        print("dump err:", str(e)[:100])

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    # ---- zed sign_in ----
    print("\n===== zed-hosted sign_in =====")
    page = ctx.new_page()
    try:
        page.goto("https://zed.dev/sign_in", wait_until="networkidle", timeout=45000)
    except Exception:
        pass
    time.sleep(6)
    dump(page, "zed sign_in")
    page.close()

    # ---- yuanbao login modal ----
    print("\n===== yuanbao-web login modal =====")
    page = ctx.new_page()
    try:
        page.goto("https://yuanbao.tencent.com/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        try:
            page.locator("button:has-text('Log In')").first.click(timeout=6000)
        except Exception:
            pass
        time.sleep(6)
        dump(page, "yuanbao modal")
        # check all frames
        for fr in page.frames:
            if fr != page.main_frame:
                try:
                    print("  FRAME:", fr.url[:100])
                except Exception:
                    pass
    finally:
        page.close()

    # ---- codebuddy login modal ----
    print("\n===== codebuddy-cn login modal =====")
    page = ctx.new_page()
    try:
        page.goto("https://www.codebuddy.cn/home/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        try:
            page.locator("button:has-text('登录')").first.click(timeout=6000)
        except Exception:
            pass
        time.sleep(6)
        dump(page, "codebuddy modal")
        for fr in page.frames:
            if fr != page.main_frame:
                try:
                    print("  FRAME:", fr.url[:100])
                except Exception:
                    pass
    finally:
        page.close()
