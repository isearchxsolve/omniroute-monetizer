"""Map the 21 chrome-only seats to live tabs across the four seat Chromes.
Zero cost: reads CDP /json only, never touches a page."""
import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CHROME_ONLY = [
    ("akool.com", "video"), ("app.heygen.com", "video"), ("chat.qwen.ai", "video"),
    ("chatglm.cn", "video"), ("claude.ai", "chat"), ("copilot.microsoft.com", "chat"),
    ("digen.ai", "video"), ("gemini.google.com", "video"), ("grok.com", "chat"),
    ("grok.com", "video"), ("labs.google", "video"), ("magichour.ai", "video"),
    ("v0.app", "chat"), ("veoaifree.com", "video"), ("www.creen.ai", "video"),
    ("www.giz.ai", "video"), ("www.meta.ai", "video"), ("www.nemovideo.com", "video"),
]

def tabs_on(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
            return [t for t in json.loads(r.read()) if t.get("type") == "page"]
    except Exception:
        return []

all_tabs = {}
for port in (9222, 9223, 9224, 9225):
    for t in tabs_on(port):
        url = t.get("url", "")
        all_tabs.setdefault(port, []).append((url, t.get("title", "")[:40]))

found = {}
for host, mod in CHROME_ONLY:
    key = (host, mod)
    found[key] = []
    for port, tabs in all_tabs.items():
        for url, title in tabs:
            if host in url:
                found[key].append((port, url[:70], title))

print("CHROME-ONLY SEATS -> LIVE TABS:")
for (host, mod), hits in sorted(found.items()):
    if hits:
        for port, url, title in hits:
            print(f"   {mod:5} {host:24} port {port}  {url}")
    else:
        print(f"   {mod:5} {host:24} NO TAB")

n_tab = sum(1 for v in found.values() if v)
print(f"\n{len(found)} chrome-only seats; {n_tab} have a live tab; {len(found)-n_tab} have NO tab")
