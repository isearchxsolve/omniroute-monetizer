"""P2 build-step 1c: FULL fresh-socket capture. Reload meta.ai, enable Network BEFORE hydration,
then type+submit a sentinel to force the lazy websocket to open, capturing handshake + init + chat
frames from the very first byte. This is the definitive socket-open sequence capture."""
import io, json, sys, time, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

SENTINEL = "Reply exactly one word: Omni."
tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
ws_events = []
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.8)
    c.call("Network.enable"); c.call("Page.enable"); c.call("Runtime.enable", timeout=20)
    def drain():
        for ev in list(c.events):
            if (ev.get("method") or "").startswith("Network.webSocket"):
                ws_events.append(ev)
        c.events.clear()

    # reload to kill any live socket, Network already enabled so we catch the reconnect
    c.call("Page.reload", {"ignoreCache": False})
    t0 = time.monotonic()
    # wait for hydration
    time.sleep(6); c.pump(1.0); drain()

    # focus composer and type sentinel
    typed = False
    for attempt in range(6):
        f = c.evaluate("""(() => { const aes=[...document.querySelectorAll('[contenteditable="true"], textarea')];
            const e=aes.find(x=>x.offsetParent)||aes[0]; if(!e) return null; e.focus();
            const r=e.getBoundingClientRect(); return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)}; })()""")
        if f:
            for k in ("mousePressed","mouseReleased"):
                c.call("Input.dispatchMouseEvent",{"type":k,"x":f["x"],"y":f["y"],"button":"left","clickCount":1})
            time.sleep(0.4)
            c.call("Input.insertText", {"text": SENTINEL})
            typed = True
            print("typed sentinel at t+%.1fs" % (time.monotonic()-t0))
            break
        time.sleep(2); c.pump(0.5); drain()
    if not typed:
        print("WARN: could not type; composer not found")

    time.sleep(1.0); c.pump(0.5); drain()
    # submit via Enter
    c.call("Input.dispatchKeyEvent", {"type":"keyDown","key":"Enter","code":"Enter","windowsVirtualKeyCode":13})
    c.call("Input.dispatchKeyEvent", {"type":"keyUp","key":"Enter","code":"Enter","windowsVirtualKeyCode":13})
    print("submitted (Enter) at t+%.1fs" % (time.monotonic()-t0))

    # watch for ws events for up to 30s
    end = time.monotonic() + 30
    while time.monotonic() < end:
        c.pump(0.7); drain()
        # stop early once we've seen a handshake + some frames
        kinds = {e.get("method") for e in ws_events}
        if "Network.webSocketHandshakeResponseReceived" in kinds and len(ws_events) > 6:
            time.sleep(3); c.pump(1.0); drain(); break

    print("\nTOTAL ws events:", len(ws_events))
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
            print("HANDSHAKE RESP:", r.get("status"), "protocol:", (r.get("headers") or {}).get("sec-websocket-protocol"))
        elif m == "Network.webSocketFrameSent":
            pl = str(((p.get("response") or {}).get("payloadData")) or "")
            print("  SENT len=%d head=%s" % (len(pl), pl[:80]))
        elif m == "Network.webSocketFrameReceived":
            pl = str(((p.get("response") or {}).get("payloadData")) or "")
            print("  RECV len=%d head=%s" % (len(pl), pl[:80]))
        elif m == "Network.webSocketClosed":
            print("  CLOSED")
    pathlib.Path("state/meta_ws_open_sequence.json").write_text(
        json.dumps([{"m": e.get("method"), "p": e.get("params")} for e in ws_events], indent=1)[:400000],
        encoding="utf-8")
    print("saved -> state/meta_ws_open_sequence.json")
finally:
    c.close()
