"""Inspect codebuddy login frame + adapta sign-in auth options."""
import time
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    # ---- codebuddy login frame ----
    print("===== codebuddy login frame =====")
    page = ctx.new_page()
    try:
        page.goto("https://www.codebuddy.cn/home/", wait_until="domcontentloaded", timeout=45000)
        time.sleep(4)
        try:
            page.locator("button:has-text('登录')").first.click(timeout=6000)
        except Exception:
            pass
        time.sleep(6)
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                print("FRAME URL:", fr.url[:120])
                txt = fr.evaluate("() => document.body ? document.body.innerText.slice(0,300) : ''")
                print("FRAME BODY:", repr(txt[:250]))
                # look for QR / wechat / google
                els = fr.evaluate("""() => Array.from(document.querySelectorAll('img,canvas,button,a')).map(e=>({tag:e.tagName, alt:(e.alt||'').slice(0,40), text:(e.innerText||'').trim().slice(0,40), src:(e.src||'').slice(0,60)})).filter(x=>x.alt||x.text||/qr|wechat|weixin|google|qq/i.test(x.src||'')).slice(0,20)""")
                for e in els:
                    print("   ", e)
            except Exception as e:
                print("frame err:", str(e)[:80])
    finally:
        page.close()

    # ---- adapta sign-in ----
    print("\n===== adapta-web sign-in =====")
    page = ctx.new_page()
    try:
        page.goto("https://agent.adapta.one/sign-in", wait_until="domcontentloaded", timeout=45000)
        time.sleep(5)
        print("URL:", page.url[:120])
        els = page.evaluate("""() => Array.from(document.querySelectorAll('button,a,input,[role=button]')).map(e=>({tag:e.tagName, type:(e.type||''), text:(e.innerText||'').trim().slice(0,45), placeholder:(e.placeholder||'').slice(0,30), href:(e.href||'').slice(0,70)})).filter(x=>x.text||x.placeholder||x.type).slice(0,25)""")
        for e in els:
            print("   ", e)
        body = page.evaluate("() => document.body ? document.body.innerText.slice(0,300) : ''")
        print("BODY:", repr(body[:250]))
    finally:
        page.close()
