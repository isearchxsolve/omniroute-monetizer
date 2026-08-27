"""v0 response-channel hunt, attempt 2: enable Network BEFORE the page (re)opens its
websocket, then send via the composer and watch every event including WS creation."""
import sys, json, time
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from capture_sessions_cdp import CDP, targets, JS_FOCUS_COMPOSER, SENTINEL

PORT = 9222
tabs = targets(PORT)
t = next((x for x in tabs if "v0.app" in x.get("url", "")), None)
if not t:
    print("no v0 tab"); sys.exit(0)
print("tab:", t["url"][:80])

c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.enable")
c.call("Network.enable")          # BEFORE reload so the WS is tracked from creation
c.call("Runtime.enable", timeout=20)

print("reloading...")
try:
    c.call("Page.reload", timeout=15)
except Exception as e:
    print("reload:", e)

# wait for load + collect events
ws_urls = []
t0 = time.time()
while time.time() - t0 < 15:
    for ev in list(c.events):
        m = ev.get("method"); prm = ev.get("params") or {}
        if m == "Network.webSocketCreated":
            u = prm.get("url", "")
            ws_urls.append(u)
            print(f"  WS-CREATED: {u[:100]}")
    time.sleep(0.3)
print(f"websockets created after reload: {len(ws_urls)}")

# focus composer + send sentinel
time.sleep(2)
focus = c.evaluate(JS_FOCUS_COMPOSER) or {}
print("composer focus ok?", focus.get("ok"))
if focus.get("ok"):
    c.call("Input.insertText", {"text": SENTINEL})
    time.sleep(0.5)
    c.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter",
                                      "code": "Enter", "windowsVirtualKeyCode": 13})
    c.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter",
                                      "code": "Enter", "windowsVirtualKeyCode": 13})
    print("sentinel submitted, watching 20s...")
    t0 = time.time()
    while time.time() - t0 < 20:
        for ev in list(c.events):
            m = ev.get("method"); prm = ev.get("params") or {}
            if m == "Network.requestWillBeSent":
                u = (prm.get("request") or {}).get("url", "")
                meth = (prm.get("request") or {}).get("method", "")
                if any(k in u for k in ("chat", "send", "stream", "completion", "api")):
                    print(f"  REQ {meth} {u[:100]}")
            elif m == "Network.webSocketFrameSent":
                pl = str((prm.get("response") or {}).get("payloadData") or "")
                print(f"  WS-SENT ({len(pl)}B): {pl[:100]!r}")
            elif m == "Network.webSocketFrameReceived":
                pl = str((prm.get("response") or {}).get("payloadData") or "")
                if "Omni" in pl or "omni" in pl.lower() or len(pl) > 40:
                    print(f"  WS-RECV ({len(pl)}B): {pl[:140]!r}")
            elif m == "Network.responseReceived":
                resp = prm.get("response") or {}
                u = resp.get("url", "")
                ct = (resp.get("headers") or {}).get("content-type", "")
                if "event-stream" in ct or any(k in u for k in ("stream", "chat", "completion")):
                    print(f"  RESP {resp.get('status')} {ct[:30]} {u[:90]}")
        time.sleep(0.3)
print("done")
