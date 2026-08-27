"""Capture the EXACT request headers the browser sends to the Felo stream endpoint."""
import json, time, urllib.request, sys
sys.path.insert(0, "scripts/automation")
import websocket

PORT = 9222
tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=10).read())
felo = [t for t in tabs if t.get("type") == "page" and "felo.ai" in (t.get("url") or "")]
if not felo:
    print("NO felo tab"); sys.exit(1)
t = felo[0]

ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
_id = 0
def call(method, params=None):
    global _id
    _id += 1
    ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == _id:
            return m.get("result", {})

call("Page.bringToFront")
call("Network.enable")

# drain
ws.settimeout(1.0)
try:
    while True: ws.recv()
except Exception: pass
ws.settimeout(30)

# Submit
call("Runtime.evaluate", {"expression": "document.querySelector('textarea, [contenteditable=\"true\"]')?.focus()", "returnByValue": True})
call("Input.insertText", {"text": "Reply exactly one word: Omni."})
time.sleep(0.3)
for typ in ("keyDown", "keyUp"):
    call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                     "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                                     **({"text": "\r"} if typ == "keyDown" else {})})

# Watch for the stream request and capture its full headers
print("--- watching for stream request ---")
end = time.monotonic() + 25
ws.settimeout(1.0)
found = False
while time.monotonic() < end and not found:
    try:
        m = json.loads(ws.recv())
    except Exception:
        continue
    if m.get("method") == "Network.requestWillBeSent":
        req = (m.get("params") or {}).get("request") or {}
        url = req.get("url", "")
        if "/stream/" in url or "message/v1" in url:
            print("URL:", url)
            print("method:", req.get("method"))
            print("headers:")
            for k, v in sorted((req.get("headers") or {}).items()):
                # redact cookie values
                if k.lower() == "cookie":
                    print(f"  {k}: <{len(v)} chars>")
                elif k.lower() == "authorization":
                    print(f"  {k}: <redacted {len(v)} chars>")
                else:
                    print(f"  {k}: {v}")
            found = True
ws.close()
if not found:
    print("stream request not seen in 25s")
