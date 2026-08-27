from DrissionPage import ChromiumPage

try:
    page = ChromiumPage(addr_or_opts='127.0.0.1:9222')
    print("DrissionPage connected successfully to Chrome on 9222!")
    print("Current URL:", page.url)
    print("Title:", page.title)
    tabs = page.tab_ids
    print(f"Total open tabs in Chrome: {len(tabs)}")
except Exception as e:
    print("DrissionPage connection error:", e)
