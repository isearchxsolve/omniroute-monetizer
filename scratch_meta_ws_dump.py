"""P2: dump ALL Network events during a reload + list workers, to find how the ws connects."""
import io, json, sys, time, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
events = []
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.8)
    c.call("Network.enable")
    c.call("Page.enable")
    # workers / targets
    try:
        tg = c.call("Target.getTargets")
        wks = [x for x in tg.get("targetInfos", []) if x.get("type") in ("service_worker","worker","shared_worker")]
        print("workers:", json.dumps([{"type":w.get("type"),"url":(w.get("url") or "")[:120]} for w in wks], indent=1)[:600])
    except Exception as e:
        print("getTargets err:", str(e)[:80])

    def drain():
        for ev in list(c.events):
            events.append(ev)
        c.events.clear()

    c.call("Page.reload", {"ignoreCache": False})
    end = time.monotonic() + 20
    while time.monotonic() < end:
        c.pump(0.6); drain()

    ws = [e for e in events if (e.get("method") or "").startswith("Network.webSocket")]
    print("\ntotal events:", len(events), "| ws events:", len(ws))
    for e in ws:
        m = e.get("method"); p = e.get("params") or {}
        if m == "Network.webSocketCreated":
            print("CREATED:", p.get("url"))
        elif m == "Network.webSocketWillSendHandshakeRequest":
            req = p.get("request") or {}
            print("HANDSHAKE url:", req.get("url"))
            for k, v in (req.get("headers") or {}).items():
                print("   %s: %s" % (k, ("<%d chars>" % len(v)) if k.lower()=="cookie" else str(v)[:140]))
        elif m == "Network.webSocketHandshakeResponseReceived":
            print("HANDSHAKE RESP:", (p.get("response") or {}).get("status"))
        else:
            print(m)
    # also any request to gateway.meta.ai over http
    gw = [e for e in events if "gateway.meta.ai" in json.dumps(e.get("params") or {})]
    print("\ngateway.meta.ai http events:", len(gw))
    for e in gw[:6]:
        print("  ", e.get("method"), json.dumps(e.get("params") or {})[:200])
finally:
    c.close()
