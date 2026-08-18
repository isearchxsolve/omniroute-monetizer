"""Visual login to grok.com: click Sign in -> find Google/X button -> SSO."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"
ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "state" / "generated_keys.json"

def handle_google(ctx):
    """Handle Google account chooser + consent across all pages."""
    for _ in range(6):
        done = True
        for pg in ctx.pages:
            try:
                u = pg.url
            except Exception:
                continue
            if "accounts.google.com" in u:
                done = False
                try:
                    acct = pg.locator("[data-email*='xxpertcomments']").first
                    if acct.count() and acct.is_visible():
                        acct.click(timeout=5000)
                        print("  clicked account chooser")
                        time.sleep(3)
                        continue
                except Exception:
                    pass
                try:
                    cont = pg.locator("button:has-text('Continue')").first
                    if cont.count() and cont.is_visible():
                        cont.click(timeout=5000)
                        print("  clicked Continue (consent)")
                        time.sleep(3)
                        continue
                except Exception:
                    pass
        if done:
            break
        time.sleep(2)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.goto("https://grok.com/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)

    # Click Sign in
    clicked = False
    for sel in ["button:has-text('Sign in')", "a:has-text('Sign in')",
                "button:has-text('Log in')", "a:has-text('Log in')",
                "[data-testid*='sign-in']", "[data-testid*='login']"]:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=5000)
                print("clicked entry:", sel)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        print("no entry button found; dumping buttons")
        btns = page.evaluate("() => Array.from(document.querySelectorAll('button,a')).map(b=>b.innerText.trim()).filter(t=>t&&t.length<40).slice(0,40)")
        print(btns)
    time.sleep(4)
    print("after entry URL:", page.url)

    # Look for Google button
    gclicked = False
    for sel in ["button:has-text('Google')", "a:has-text('Google')",
                "button:has-text('Continue with Google')", "a:has-text('Continue with Google')",
                "[data-provider*='google']", "button:has-text('Sign in with Google')"]:
        try:
            el = page.locator(sel).first
            if el.count() and el.is_visible():
                el.click(timeout=5000)
                print("clicked google:", sel)
                gclicked = True
                break
        except Exception:
            continue
    if not gclicked:
        print("no google button; dumping visible buttons/links")
        btns = page.evaluate("() => Array.from(document.querySelectorAll('button,a')).map(b=>b.innerText.trim()).filter(t=>t&&t.length<50).slice(0,50)")
        print(btns)
    time.sleep(5)

    # Handle Google chooser/consent
    handle_google(ctx)
    time.sleep(5)

    # Check result
    page2 = None
    for pg in ctx.pages:
        if "grok.com" in pg.url:
            page2 = pg
    if page2 is None:
        page2 = page
    page2.bring_to_front()
    time.sleep(3)
    print("final URL:", page2.url)

    cookies = ctx.cookies(["https://grok.com"])
    names = [c["name"] for c in cookies]
    strong = [n for n in ["sso", "sso-rw"] if n in names]
    print("cookie count:", len(cookies), "strong:", strong)

    body = page2.evaluate("() => document.body ? document.body.innerText.slice(0,200) : ''")
    print("BODY:", repr(body[:150]))

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
        print("NO sso cookie — login did not complete")
