"""Attach to the open Felo tab, submit a short message, record ALL network requests for 20s
to discover the stream endpoint that follows the bootstrap POST."""
import json, time, urllib.request, sys
sys.path.insert(0, "scripts/automation")
import websocket

PORT = 9222
tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=10).read())
felo = [t for t in tabs if t.get("type") == "page" and "felo.ai" in (t.get("url") or "")]
if not felo:
    print("NO felo tab"); sys.exit(1)
t = felo[0]
print("tab:", t["url"][:100])

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
call("Runtime.enable")
call("Network.enable")

# drain a moment
ws.settimeout(1.0)
try:
    while True: ws.recv()
except Exception: pass
ws.settimeout(30)

# Submit a short message via the composer
JS_SUBMIT = r"""
(() => {
  const ta = document.querySelector('textarea, [contenteditable="true"]');
  if (!ta) return {ok:false, error:'no composer'};
  ta.focus();
  return {ok:true};
})()
"""
r = call("Runtime.evaluate", {"expression": JS_SUBMIT, "returnByValue": True})
print("focus:", r.get("result", {}).get("value"))

# insert text + enter
call("Input.insertText", {"text": "Reply exactly one word: Omni."})
time.sleep(0.3)
for typ in ("keyDown", "keyUp"):
    call("Input.dispatchKeyEvent", {"type": typ, "key": "Enter", "code": "Enter",
                                     "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                                     **({"text": "\r"} if typ == "keyDown" else {})})

# Record all requests for 20s
print("\n--- network for 20s ---")
end = time.monotonic() + 20
seen = set()
ws.settimeout(1.0)
while time.monotonic() < end:
    try:
        m = json.loads(ws.recv())
    except Exception:
        continue
    if m.get("method") == "Network.requestWillBeSent":
        req = (m.get("params") or {}).get("request") or {}
        url = req.get("url", "")
        method = req.get("method", "")
        if url in seen: continue
        seen.add(url)
        if any(x in url for x in ("analytics", "sentry", "google", "facebook", ".png", ".css", ".js", ".woff")):
            continue
        print(f"  {method:6s} {url[:140]}")
        body = req.get("postData", "")
        if body and len(body) < 600:
            print(f"         body: {body[:300]}")
ws.close()
print("\ndone")
