"""Click the Google account row (LI), handle consent, then harvest grok sso cookie."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"
ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "state" / "generated_keys.json"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    g = None
    for pg in ctx.pages:
        if "accounts.google.com" in pg.url:
            g = pg
            break
    if g is None:
        print("no google page")
        raise SystemExit
    g.bring_to_front()
    time.sleep(1)

    # Click the account row — the LI element
    clicked = False
    for sel in [
        "li:has([data-email*='xxpertcomments'])",
        "[data-email*='xxpertcomments']",
    ]:
        try:
            el = g.locator(sel).first
            if el.count():
                el.click(timeout=6000)
                print("clicked account via:", sel)
                clicked = True
                break
        except Exception as e:
            print("sel failed:", sel, str(e)[:60])
    if not clicked:
        # JS fallback click the LI
        r = g.evaluate("""() => {
            const li = Array.from(document.querySelectorAll('li')).find(e => /xxpertcomments/i.test(e.innerText||''));
            if (li) { li.click(); return 'li-clicked'; }
            const d = document.querySelector('[data-email*="xxpertcomments"]');
            if (d) { d.click(); return 'div-clicked'; }
            return null;
        }""")
        print("JS fallback:", r)
    time.sleep(5)

    # Handle consent / password / continue across google pages
    for rnd in range(10):
        acted = False
        for pg in list(ctx.pages):
            try:
                u = pg.url
            except Exception:
                continue
            if "accounts.google.com" not in u:
                continue
            # consent Continue button
            for bsel in ["button:has-text('Continue')", "#submit_approve_access",
                         "button:has-text('Allow')", "button:has-text('Next')"]:
                try:
                    b = pg.locator(bsel).first
                    if b.count() and b.is_visible():
                        b.click(timeout=5000)
                        print(f"  clicked {bsel}")
                        acted = True
                        time.sleep(3)
                        break
                except Exception:
                    continue
            # account chooser again?
            try:
                acct = pg.locator("[data-email*='xxpertcomments']").first
                if acct.count() and acct.is_visible():
                    acct.click(timeout=5000)
                    print("  re-clicked account chooser")
                    acted = True
                    time.sleep(3)
            except Exception:
                pass
        if not acted:
            time.sleep(2)
    time.sleep(5)

    # find grok page
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
        print("NO sso cookie yet")
        for pg in ctx.pages:
            try:
                print("  page:", pg.url[:100])
            except Exception:
                pass
