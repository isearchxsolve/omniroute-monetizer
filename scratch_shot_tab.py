"""Screenshot one specific tab by URL substring, via raw CDP (no playwright attach-all)."""
import base64
import json
import pathlib
import sys
import urllib.request

import websocket


def shot(port: int, url_substr: str, out: str) -> None:
    data = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5).read())
    tab = next((t for t in data if t.get("type") == "page" and url_substr in (t.get("url") or "")), None)
    if not tab:
        print(f"NO TAB matching {url_substr!r} on port {port}")
        return
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30)
    mid = 0

    def send(method, params=None):
        nonlocal mid
        mid += 1
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == mid:
                return msg

    r = send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
    ws.close()
    if "result" not in r:
        print("screenshot failed:", json.dumps(r)[:200])
        return
    pathlib.Path(out).write_bytes(base64.b64decode(r["result"]["data"]))
    print(f"OK {out}  title={tab.get('title','')[:80]}")


if __name__ == "__main__":
    shot(int(sys.argv[1]), sys.argv[2], sys.argv[3])
