import json
import urllib.request
from playwright.sync_api import sync_playwright

info = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/version").read())
ws_url = info["webSocketDebuggerUrl"]
print("Target WS URL:", ws_url)

with sync_playwright() as p:
    try:
        browser = p.chromium.connect_over_cdp(ws_url, headers={"Host": "127.0.0.1:9222"})
        print("CONNECTED SUCCESSFULLY!")
        print("Contexts:", len(browser.contexts))
        print("Pages:", len(browser.contexts[0].pages))
    except Exception as e:
        print("ERROR:", e)
