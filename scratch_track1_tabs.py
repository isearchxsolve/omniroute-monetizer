import sys, json, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PORTS = [9222, 9223, 9224, 9225]
WANT = ["meta.ai", "claude.ai", "copilot.microsoft.com", "grok.com", "v0.app",
        "cerebras", "deepseek", "gemini.google.com", "chatglm"]

for port in PORTS:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5) as r:
            targets = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        print(f"\nport {port}: DOWN ({e})")
        continue
    pages = [t for t in targets if t.get("type") == "page"]
    print(f"\n===== port {port}: {len(pages)} pages =====")
    for t in pages:
        url = t.get("url", "")
        title = t.get("title", "")[:40]
        hit = any(w in url for w in WANT)
        mark = " <<<" if hit else ""
        print(f"  {url[:80]:80} | {title}{mark}")
