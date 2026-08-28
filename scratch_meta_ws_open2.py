"""P2 build-step 1b: reload meta.ai tab, then watch 45s (with a composer interaction at t+15s)
for the lazy websocket connect; capture handshake URL + headers + first frames."""
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
    c.call("Network.enable"); c.call("Page.enable")
    def drain():
        for ev in list(c.events):
            if (ev.get("method") or "").startswith("Network.webSocket"):
                ws_events.append(ev)
        c.events.clear()

    c.call("Page.reload", {"ignoreCache": False})
    t0 = time.monotonic()
    interacted = False
    while time.monotonic() - t0 < 45:
        c.pump(0.7); drain()
        if ws_events:
            print("ws event at t+%.1fs" % (time.monotonic()-t0)); break
        if not interacted and time.monotonic() - t0 > 15:
            interacted = True
            try:
                c.call("Runtime.enable", timeout=15)
                f = c.evaluate("""(() => { const aes=[...document.querySelectorAll('[contenteditable="true"], textarea')];
                    const e=aes.find(x=>x.offsetParent)||aes[0]; if(!e) return null; e.focus();
                    const r=e.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; })()""")
                if f:
                    for k in ("mousePressed","mouseReleased"):
                        c.call("Input.dispatchMouseEvent",{"type":k,"x":f["x"],"y":f["y"],"button":"left","clickCount":1})
                    print("interacted (clicked composer) at t+%.1fs" % (time.monotonic()-t0))
            except Exception as e:
                print("interaction note:", str(e)[:80])

    print("\nws events:", len(ws_events))
    for ev in ws_events:
        m = ev.get("method"); p = ev.get("params") or {}
        if m == "Network.webSocketCreated":
            print("CREATED:", p.get("url"))
        elif m == "Network.webSocketWillSendHandshakeRequest":
            req = p.get("request") or {}
            print("HANDSHAKE url:", req.get("url"))
            for k, v in (req.get("headers") or {}).items():
                print("   %s: %s" % (k, ("<%d chars>" % len(v)) if k.lower()=="cookie" else str(v)[:160]))
        elif m == "Network.webSocketHandshakeResponseReceived":
            r = p.get("response") or {}
            print("HANDSHAKE RESP:", r.get("status"))
        else:
            pl = str(((p.get("response") or {}).get("payloadData")) or "")
            print("  %s len=%d head=%s" % (m.split("webSocket")[-1], len(pl), pl[:70]))
    pathlib.Path("state/meta_ws_open_sequence.json").write_text(
        json.dumps([{"m": e.get("method"), "p": e.get("params")} for e in ws_events], indent=1)[:300000],
        encoding="utf-8")
    print("saved -> state/meta_ws_open_sequence.json")
finally:
    c.close()
