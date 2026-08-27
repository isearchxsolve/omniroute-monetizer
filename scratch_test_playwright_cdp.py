from playwright.sync_api import sync_playwright

try:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        print("Connected successfully via Playwright Python!")
        ctx = browser.contexts[0]
        print(f"Number of contexts: {len(browser.contexts)}")
        print(f"Number of open pages in context: {len(ctx.pages)}")
        for idx, page in enumerate(ctx.pages[:10]):
            print(f"  Page {idx+1}: {page.url} - {page.title()}")
except Exception as e:
        print("Error connecting Playwright over CDP:", e)
