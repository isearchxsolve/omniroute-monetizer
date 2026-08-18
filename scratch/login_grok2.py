"""Attach to the accounts.x.ai sign-in page, click Login with Google, complete SSO, harvest sso cookie."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"
ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "state" / "generated_keys.json"

def handle_google_pages(ctx, rounds=8):
    """Click account chooser + consent on any accounts.google.com page (incl popups)."""
    for _ in range(rounds):
        acted = False
        for pg in list(ctx.pages):
            try:
                u = pg.url
            except Exception:
                continue
            if "accounts.google.com" not in u:
                continue
            # account chooser
            try:
                acct = pg.locator("[data-email*='xxpertcomments']").first
                if acct.count() and acct.is_visible():
                    acct.click(timeout=5000)
                    print("  clicked account chooser")
                    acted = True
                    time.sleep(3)
                    continue
            except Exception:
                pass
            # consent Continue
            try:
                cont = pg.locator("button:has-text('Continue')").first
                if cont.count() and cont.is_visible():
                    cont.click(timeout=5000)
                    print("  clicked Continue (consent)")
                    acted = True
                    time.sleep(3)
                    continue
            except Exception:
                pass
        if not acted:
            time.sleep(2)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    # find the x.ai sign-in page
    xai = None
    for pg in ctx.pages:
        if "accounts.x.ai" in pg.url:
            xai = pg
            break
    if xai is None:
        print("no accounts.x.ai page; opening")
        xai = ctx.new_page()
        xai.goto("https://grok.com/", wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
        try:
            xai.locator("button:has-text('Sign in')").first.click(timeout=5000)
        except Exception:
            pass
        time.sleep(4)

    xai.bring_to_front()
    print("xai URL:", xai.url)

    # Click Login with Google — try multiple strategies, watch for popup
    popup_holder = {}
    def on_popup(pg):
        print("  POPUP opened:", pg.url[:80])
        popup_holder["pg"] = pg
    ctx.on("page", on_popup)

    clicked = False
    for sel in [
        "button:has-text('Login with Google')",
        "a:has-text('Login with Google')",
        "text=Login with Google",
        "button:has-text('Google')",
        "a:has-text('Google')",
    ]:
        try:
            el = xai.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=6000)
                print("clicked google via:", sel)
                clicked = True
                break
        except Exception as e:
            continue
    if not clicked:
        # JS fallback: click any element whose text contains 'Google'
        r = xai.evaluate("""() => {
            const els = Array.from(document.querySelectorAll('button,a,div[role=button],span[role=button]'));
            const t = els.find(e => /google/i.test(e.innerText||''));
            if (t) { t.click(); return (t.tagName||'?') + ':' + (t.innerText||'').trim().slice(0,30); }
            return null;
        }""")
        print("JS fallback clicked:", r)
        clicked = bool(r)

    time.sleep(5)
    handle_google_pages(ctx)
    time.sleep(6)
    handle_google_pages(ctx)
    time.sleep(5)

    # find grok.com page now
    grok = None
    for pg in ctx.pages:
        try:
            if "grok.com" in pg.url:
                grok = pg
        except Exception:
            pass
    if grok:
        grok.bring_to_front()
        time.sleep(3)
        print("grok URL:", grok.url)

    cookies = ctx.cookies(["https://grok.com"])
    names = [c["name"] for c in cookies]
    strong = [n for n in ["sso", "sso-rw"] if n in names]
    print("cookie count:", len(cookies), "strong:", strong)

    if strong:
        header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        data = json.loads(KEYS.read_text(encoding="utf-8")) if KEYS.exists() else {}
        data["cookie_header:grok-web"] = {
            "cookie_header": header,
            "cookie_names": names,
            "strong": strong,
            "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "grok.com visual login via CDP 9223",
        }
        KEYS.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print("SAVED grok-web cookie header, len:", len(header))
    else:
        print("NO sso cookie yet — login incomplete")
        # dump current pages for diagnosis
        for pg in ctx.pages:
            try:
                print("  page:", pg.url[:100])
            except Exception:
                pass
