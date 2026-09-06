"""Recover the lighthouse clip's signed CDN URL via CDP Network events.

Raw websocket to the P2 tab: Network.enable -> click newest tile -> collect
Network.responseReceived / loadingFinished URLs matching flow-content.google/video/.
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\omniroute-monetizer\scripts\automation")
import websocket

CLICK_TILE = r"""
(() => {
  const vids = Array.from(document.querySelectorAll('video'));
  if (!vids.length) return JSON.stringify({ok: false, why: 'no tiles'});
  const v = vids[vids.length - 1];
  v.scrollIntoView({block: 'center'});
  const card = v.closest('[role="button"], button, [tabindex]') || v;
  card.click();
  return JSON.stringify({ok: true, tiles: vids.length});
})()
"""

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
send("Network.enable", {"maxTotalBufferSize": 100000000,
                        "maxResourceBufferSize": 50000000})
send("Runtime.evaluate", {"expression": CLICK_TILE, "returnByValue": True})

urls = set()
deadline = time.time() + 60
while time.time() < deadline:
    try:
        ws.settimeout(max(1.0, deadline - time.time()))
        msg = json.loads(ws.recv())
    except websocket.WebSocketTimeoutException:
        continue
    except Exception:
        break
    method = msg.get("method", "")
    if method in ("Network.responseReceived", "Network.requestWillBeSent"):
        u = (msg["params"].get("response", msg["params"]).get("url")
             or msg["params"].get("request", {}).get("url") or "")
        if "flow-content.google/video/" in u:
            urls.add(u)
    if method == "Network.loadingFailed":
        pass

ws.close()
print(f"captured {len(urls)} flow-content URL(s):")
for u in sorted(urls):
    print(u[:200])

for u in sorted(urls):
    try:
        req = urllib.request.Request(u, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            print("HEAD:", r.status, r.headers.get("Content-Type"),
                  r.headers.get("Content-Length"), u[:90])
    except Exception as e:
        print("HEAD error:", str(e)[:120])
