"""P2 recon part 3: is the seat Chrome on 9222 alive, and does it have a meta.ai tab? (read-only CDP)"""
import io, json, sys, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

for port in (9222, 9223, 9224, 9225):
    try:
        r = urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=3)
        tabs = json.loads(r.read())
        pages = [t for t in tabs if t.get("type") == "page"]
        print("port %d: ALIVE, %d pages" % (port, len(pages)))
        for t in pages:
            url = t.get("url") or ""
            if any(h in url for h in ("meta.ai", "meta.com")):
                print("   META TAB:", url[:100], "| title:", (t.get("title") or "")[:60], "| ws:", bool(t.get("webSocketDebuggerUrl")))
    except Exception as e:
        print("port %d: down (%s)" % (port, type(e).__name__))
