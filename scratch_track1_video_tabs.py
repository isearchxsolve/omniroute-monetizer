import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORTS = [9222, 9223, 9224, 9225]

# The 20 chrome-runtime VIDEO seats from the transport audit (host substrings).
VIDEO_HOSTS = [
    "akool.com", "app.heygen.com", "chat.qwen.ai", "chatglm.cn", "digen.ai",
    "gemini.google.com", "grok.com", "labs.google", "magichour.ai", "v0.app",
    "veoaifree.com", "www.creen.ai", "www.giz.ai", "www.meta.ai", "www.nemovideo.com",
]

found = {}
for port in PORTS:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5) as r:
            targets = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"port {port}: DOWN ({e})")
        continue
    pages = [t for t in targets if t.get("type") == "page"]
    for t in pages:
        url = t.get("url", "")
        for h in VIDEO_HOSTS:
            if h in url:
                found.setdefault(h, []).append((port, url[:70], t.get("title", "")[:30]))

print("=== VIDEO SEATS WITH LIVE TABS ===")
for h in VIDEO_HOSTS:
    if h in found:
        for port, url, title in found[h]:
            print(f"  {h:22} port {port}  {url}  | {title}")
    else:
        print(f"  {h:22} NO LIVE TAB")
