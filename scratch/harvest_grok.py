"""Navigate grok.com, check login, harvest full cookie header incl cf_clearance."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9223"
ROOT = Path(__file__).resolve().parent.parent
KEYS = ROOT / "state" / "generated_keys.json"

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.goto("https://grok.com/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(6)

    url = page.url
    title = page.title()
    body = page.evaluate("() => document.body ? document.body.innerText.slice(0,300) : ''")
    print("URL:", url)
    print("TITLE:", title)
    print("BODY:", repr(body[:200]))

    cookies = ctx.cookies(["https://grok.com"])
    names = [c["name"] for c in cookies]
    print("\ncookie count:", len(cookies))
    print("cookie names:", names)

    strong = [n for n in ["sso", "sso-rw", "cf_clearance", "__cf_bm"] if n in names]
    print("strong present:", strong)

    # build full cookie header
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    print("header len:", len(header))

    # save (T11: no values printed)
    data = {}
    if KEYS.exists():
        data = json.loads(KEYS.read_text(encoding="utf-8"))
    data["cookie_header:grok-web"] = {
        "cookie_header": header,
        "cookie_names": names,
        "strong": strong,
        "harvested_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "grok.com via CDP 9223",
        "logged_in_url": url,
    }
    KEYS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("saved cookie_header:grok-web")

    page.close()
