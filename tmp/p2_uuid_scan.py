"""Inspect the 10 batchexecute response bodies for media-id JSON (not URL-shaped)."""
import json
import re
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
send("Page.navigate", {"url": tab["url"]})

snippets = []
deadline = time.time() + 45
while time.time() < deadline:
    try:
        ws.settimeout(max(1.0, deadline - time.time()))
        msg = json.loads(ws.recv())
    except (websocket.WebSocketTimeoutException, Exception):
        continue
    if msg.get("method") == "Network.responseReceived":
        p = msg["params"]
        u = p["response"]["url"]
        if "batchexecute" in u:
            rid = p["requestId"]
            try:
                body = send("Network.getResponseBody", {"requestId": rid})
                content = body.get("body", "")
                hits = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                                  content)
                snippets.append({"url_tail": u[-60:], "len": len(content),
                                 "uuids": sorted(set(hits))[:12]})
            except Exception as e:
                snippets.append({"url_tail": u[-60:], "err": str(e)[:60]})

ws.close()
for s in snippets:
    print(json.dumps(s))
