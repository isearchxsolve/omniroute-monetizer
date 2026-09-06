"""Read Flow's Angular state: the media list (batchexecute cPZSdc payload) holds the
signed CDN URLs. Try IndexedDB/localStorage scan + the network-captured batchexecute
response via CDP Network on the RELOAD (the app fetches the media list at boot).
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
import websocket

targets = json.loads(urllib.request.urlopen(
    "http://127.0.0.1:9226/json/list", timeout=10).read())
tab = next(t for t in targets if t.get("type") == "page"
           and "flow.google.com/project/" in t.get("url", ""))
ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30,
                                 max_size=64 * 1024 * 1024)
mid = 0


def send(method, params=None):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == mid:
            return msg.get("result", {})


send("Page.bringToFront")
send("Network.enable")
# Reload the page and capture ALL response bodies, keeping any flow-content.google URL
send("Page.navigate", {"url": tab["url"]})

urls = {}
deadline = time.time() + 60
bodies_tried = 0
while time.time() < deadline:
    try:
        ws.settimeout(max(1.0, deadline - time.time()))
        msg = json.loads(ws.recv())
    except websocket.WebSocketTimeoutException:
        continue
    except Exception:
        break
    if msg.get("method") == "Network.responseReceived":
        p = msg["params"]
        u = p["response"]["url"]
        if "batchexecute" in u or "flow.google.com" in u:
            rid = p["requestId"]
            try:
                body = send("Network.getResponseBody", {"requestId": rid})
                bodies_tried += 1
                content = body.get("body", "")
                import re
                for m in re.finditer(
                        r"https://flow-content\.google/video/[0-9a-f-]{36}\?[A-Za-z0-9=&%_\-]+",
                        content):
                    urls[m.group(0)] = u[:80]
            except Exception:
                pass
    if msg.get("method") in ("Network.loadingFailed",):
        pass

ws.close()
print(f"bodies inspected: {bodies_tried}; flow-content video urls found: {len(urls)}")
for u, src in urls.items():
    print(f"  {u[:180]}  (from {src})")
