"""Scan every open tab on all CDP ports for the lighthouse sentinel in the live DOM."""
import json
import sys
import urllib.request

import websocket

SENTINEL = "Omni sentinel shot: a lone lighthouse beam sweeping across dark ocean waves at midnight"
PORTS = [int(p) for p in sys.argv[1:]] or [9222]

JS_CHECK = r"""
(() => {
  const s = %s;
  const body = document.body ? document.body.innerText : '';
  const inBody = body.includes(s);
  const inTitle = document.title.includes('lighthouse') || document.title.includes('Lighthouse');
  const inputs = [...document.querySelectorAll('textarea,[contenteditable="true"]')];
  const inComposer = inputs.some(el => (el.value || el.innerText || '').includes(s));
  return JSON.stringify({inBody, inTitle, inComposer, url: location.href, title: document.title});
})()
""" % json.dumps(SENTINEL)

total_hits = 0
for port in PORTS:
    try:
        data = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5).read())
    except Exception as e:
        print(f"PORT {port}: unreachable ({e})")
        continue
    pages = [t for t in data if t.get("type") == "page"]
    print(f"\n=== PORT {port}: {len(pages)} page tabs ===")
    for t in pages:
        ws_url = t.get("webSocketDebuggerUrl")
        if not ws_url:
            continue
        try:
            ws = websocket.create_connection(ws_url, timeout=8)
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": JS_CHECK, "returnByValue": True}}))
            res = None
            import time
            deadline = time.time() + 8
            while time.time() < deadline:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    res = msg
                    break
            ws.close()
            if not res or "result" not in res:
                continue
            val = res["result"].get("result", {}).get("value")
            if not val:
                continue
            info = json.loads(val)
            if info["inBody"] or info["inComposer"]:
                total_hits += 1
                where = "COMPOSER" if info["inComposer"] else "BODY"
                print(f"  [HIT:{where}] {info['title'][:70]} | {info['url'][:90]}")
        except Exception:
            continue

print(f"\nTOTAL sentinel-bearing tabs: {total_hits}")
