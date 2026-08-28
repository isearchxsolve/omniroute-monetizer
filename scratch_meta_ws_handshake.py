"""P2: capture meta.ai websocket handshake (URL + headers) by enabling Network BEFORE reload.
Read-only on state; reloads the seat's own tab (normal operation).
"""
import io, json, sys, time, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
ws_events = []
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.8)
    c.call("Network.enable")
    def drain():
        for ev in list(c.events):
            m = ev.get("method"); p = ev.get("params") or {}
            if m and m.startswith("Network.webSocket"):
                ws_events.append((m, p))
    # reload to force ws reconnect
    c.call("Page.reload", {"ignoreCache": False})
    end = time.monotonic() + 18
    while time.monotonic() < end:
        c.pump(0.6); drain()
        # stop early once we have a handshake request
        if any(m == "Network.webSocketWillSendHandshakeRequest" for m, _ in ws_events):
            time.sleep(2); drain(); break

    print("ws events captured:", len(ws_events))
    for m, p in ws_events:
        if m == "Network.webSocketCreated":
            print("\nCREATED url:", p.get("url"))
            print("  initiator:", json.dumps(p.get("initiator") or {})[:200])
        elif m == "Network.webSocketWillSendHandshakeRequest":
            req = (p.get("request") or {})
            print("\nHANDSHAKE REQUEST:")
            print("  url:", req.get("url"))
            hdrs = req.get("headers") or {}
            for k, v in hdrs.items():
                if k.lower() in ("cookie",):
                    print("  %s: <%d chars, %d cookies>" % (k, len(v), v.count(";")+1))
                else:
                    print("  %s: %s" % (k, str(v)[:160]))
        elif m == "Network.webSocketHandshakeResponseReceived":
            resp = (p.get("response") or {})
            print("\nHANDSHAKE RESPONSE status:", resp.get("status"), resp.get("statusText"))
            for k, v in (resp.get("headers") or {}).items():
                print("  %s: %s" % (k, str(v)[:120]))
    # save full
    pathlib.Path("state/meta_ws_handshake.json").write_text(
        json.dumps([{"m": m, "p": p} for m, p in ws_events], indent=1)[:200000], encoding="utf-8")
    print("\nsaved -> state/meta_ws_handshake.json")
finally:
    c.close()
