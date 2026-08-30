"""Navigate the 4 HARNESS_NAVIGATE tabs to their chat surfaces, with per-tab retry.
Uses the same CDP + safety rules as the harness (automation profile on :9222 only).
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
import websocket  # noqa: E402

PORT = 9222
NAV = {
    "Groq Chat": ("https://console.groq.com/playground", "groq.com"),
    "Baichuan Web": ("https://yi.baichuan-ai.com/", "baichuan-ai.com"),
}


def targets():
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=10).read())


def host_of(url):
    try:
        return urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return ""


import urllib.parse  # noqa: E402

for name, (url, registered) in NAV.items():
    tab = next((t for t in targets()
                if t.get("type") == "page"
                and (host_of(t.get("url") or "") == registered
                     or (host_of(t.get("url") or "") or "").endswith("." + registered))), None)
    if not tab:
        print(f"  no-tab   {name}")
        continue
    ws_url = tab["webSocketDebuggerUrl"]
    done = False
    for attempt in (1, 2, 3):
        try:
            ws = websocket.create_connection(ws_url, timeout=30)
            ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
            _ = ws.recv()
            ws.close()
            done = True
            break
        except Exception as e:
            print(f"  retry{attempt} {name}: {type(e).__name__}")
            time.sleep(3)
    print(f"  {'nav-ok  ' if done else 'FAILED  '} {name} -> {url}")
    time.sleep(4)

time.sleep(15)
print("\nsettled URLs:")
for t in targets():
    if t.get("type") == "page":
        print(f"  {t.get('url','')[:90]}")
