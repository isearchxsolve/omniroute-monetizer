"""Tiny CDP helper for the video harvest: click, type, screenshot, read page text.
Usage: python cdp_click.py <port> <js-selector-action>
Actions are passed as JSON on stdin. Designed for one-off harvest steps with
screenshots between each click (rule 11: never blind-click).
"""
import base64
import json
import pathlib
import sys
import time
import urllib.request

import websocket


def connect(port, match):
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list"))
    t = next(t for t in tabs if match in (t.get("url") or "")) if match else tabs[0]
    ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=20)
    return ws, t


def call(ws, method, params, _id=[0]):
    _id[0] += 1
    ws.send(json.dumps({"id": _id[0], "method": method, "params": params}))
    end = time.time() + 20
    while time.time() < end:
        r = json.loads(ws.recv())
        if r.get("id") == _id[0]:
            if "error" in r:
                raise RuntimeError(r["error"])
            return r.get("result", {})
    raise RuntimeError("cdp timeout")


def main():
    port, match = int(sys.argv[1]), sys.argv[2]
    action = sys.stdin.read()
    spec = json.loads(action)
    ws, tab = connect(port, match)
    call(ws, "Page.enable", {})
    out = {}
    if spec.get("eval"):
        r = call(ws, "Runtime.evaluate",
                 {"expression": spec["eval"], "returnByValue": True,
                  "awaitPromise": bool(spec.get("await"))})
        out["result"] = r.get("result", {}).get("value")
        if r.get("exceptionDetails"):
            out["exc"] = str(r["exceptionDetails"].get("exception", {}).get("description"))[:200]
    if spec.get("sleep"):
        time.sleep(spec["sleep"])
    if spec.get("shot"):
        s = call(ws, "Page.captureScreenshot", {"format": "png"})
        p = pathlib.Path(spec["shot"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(s["data"]))
        out["shot"] = str(p)
    print(json.dumps(out)[:2000])
    ws.close()


if __name__ == "__main__":
    main()
