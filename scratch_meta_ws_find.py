"""P2 build-step 2: find the live meta.ai WebSocket via Runtime.queryObjects (heap scan —
finds sockets in module closures that window-walking misses), read its exact URL, then close
it to force a reconnect WHILE Network.enable is active, capturing webSocketCreated (exact URL)
+ webSocketWillSendHandshakeRequest (auth headers) + first frames.
"""
import io, json, sys, time, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

OUT = pathlib.Path("state/meta_ws_find.json")

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
if not tabs:
    print("NO meta.ai tab on 9222"); raise SystemExit(1)
t = tabs[0]
print("tab:", t.get("url"))
c = CDP(t["webSocketDebuggerUrl"])
result = {"tab": t.get("url"), "sockets": [], "reconnect": {}}
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.8)
    c.call("Runtime.enable", timeout=25)
    c.call("Network.enable")

    # 1) heap scan for live WebSocket instances
    proto = c.call("Runtime.evaluate",
                   {"expression": "WebSocket.prototype", "returnByValue": False})
    oid = (proto.get("result") or {}).get("objectId")
    if not oid:
        print("could not get WebSocket.prototype objectId"); raise SystemExit(1)
    objs = c.call("Runtime.queryObjects", {"prototypeObjectId": oid})
    arr = (objs.get("objects") or {}).get("objectId")
    if not arr:
        print("queryObjects returned nothing"); raise SystemExit(1)

    # describe each instance
    desc = c.call("Runtime.callFunctionOn", {
        "objectId": arr,
        "returnByValue": True,
        "functionDeclaration": """function() {
            return this.map(ws => {
                let info = {url: '', readyState: -1, protocol: '', extensions: '', buffered: 0};
                try { info.url = ws.url; } catch(e){}
                try { info.readyState = ws.readyState; } catch(e){}
                try { info.protocol = ws.protocol; } catch(e){}
                try { info.extensions = ws.extensions; } catch(e){}
                try { info.buffered = ws.bufferedAmount; } catch(e){}
                return info;
            });
        }"""})
    sockets = (desc.get("result") or {}).get("value") or []
    result["sockets"] = sockets
    print("live WebSocket instances:", len(sockets))
    for s in sockets:
        print("  url:", s.get("url"))
        print("  readyState:", s.get("readyState"), "(1=OPEN) | protocol:", repr(s.get("protocol")),
              "| buffered:", s.get("buffered"))

    meta_socks = [s for s in sockets if "gateway" in (s.get("url") or "") or "meta" in (s.get("url") or "")]
    if not meta_socks:
        print("no meta/gateway socket among live instances — saving and stopping")
        OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        raise SystemExit(0)

    # 2) close the gateway socket to force a reconnect; Network.enable is already active so
    #    webSocketCreated + handshake events will fire this time.
    closed = c.call("Runtime.callFunctionOn", {
        "objectId": arr,
        "returnByValue": True,
        "functionDeclaration": """function() {
            let n = 0;
            for (const ws of this) {
                try {
                    if ((ws.url || '').includes('gateway') && ws.readyState <= 1) { ws.close(); n++; }
                } catch(e){}
            }
            return n;
        }"""})
    print("closed gateway sockets:", (closed.get("result") or {}).get("value"))

    # 3) pump for reconnect events (drain c.events as they arrive; stop early once we have
    #    a created-socket + at least one frame, after a short settle)
    t0 = time.monotonic()
    created, handshake_req, handshake_resp, frames = [], [], [], []
    got_at = None
    while time.monotonic() - t0 < 45:
        c.pump(1.0)
        while c.events:
            ev = c.events.pop(0)
            m = ev.get("method"); p = ev.get("params") or {}
            if m == "Network.webSocketCreated":
                created.append({"url": p.get("url"), "initiator": p.get("initiator")})
            elif m == "Network.webSocketWillSendHandshakeRequest":
                handshake_req.append((p.get("request") or {}).get("headers"))
            elif m == "Network.webSocketHandshakeResponseReceived":
                handshake_resp.append((p.get("response") or {}).get("headers"))
            elif m in ("Network.webSocketFrameSent", "Network.webSocketFrameReceived"):
                d = (p.get("response") or {})
                frames.append({"dir": "sent" if m.endswith("Sent") else "recv",
                               "len": len(d.get("payloadData") or ""),
                               "head": (d.get("payloadData") or "")[:80]})
        if created and frames and got_at is None:
            got_at = time.monotonic()
        if got_at and time.monotonic() - got_at > 4:
            break
    result["reconnect"] = {"created": created, "handshakeRequestHeaders": handshake_req,
                           "handshakeResponseHeaders": handshake_resp,
                           "firstFrames": frames[:20],
                           "waitedSeconds": round(time.monotonic() - t0, 1)}
    print("\nreconnect created:", json.dumps(created, indent=1)[:600])
    if handshake_req:
        print("handshake REQUEST headers (names):", sorted(handshake_req[0].keys()))
        h = handshake_req[0]
        for k in ("Cookie", "cookie", "Origin", "Sec-WebSocket-Protocol", "User-Agent"):
            if k in h:
                v = h[k]
                print("   %s: %s" % (k, (v[:80] + "...(%d chars)" % len(v)) if len(v) > 80 else v))
    print("first frames:", len(frames))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print("saved ->", OUT)
finally:
    c.close()
