"""P2 build-step 1: capture meta.ai ws socket-OPEN sequence. Find the live WebSocket in the page,
hook WebSocket to record the next connect (url + first frames), close the live socket to force a
reconnect, then capture handshake + initial frame exchange. Read-only on state.
"""
import io, json, sys, time, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.8)
    c.call("Runtime.enable", timeout=25)
    c.call("Network.enable")

    # 1) find live websockets by walking window (shallow) + common containers
    found = c.evaluate("""(() => {
      const out = [];
      const seen = new Set();
      function visit(obj, path, depth) {
        if (!obj || depth > 3 || seen.has(obj)) return;
        try { seen.add(obj); } catch(e){ return; }
        for (const k of Object.getOwnPropertyNames(obj)) {
          let v; try { v = obj[k]; } catch(e){ continue; }
          if (v instanceof WebSocket) {
            out.push({path: path + '.' + k, url: v.url, readyState: v.readyState, protocol: v.protocol});
          } else if (v && typeof v === 'object' && depth < 3 && !(v instanceof Element)
                     && !(v instanceof Window) && out.length < 20) {
            // only descend into plain-ish objects
            try { if (v.constructor === Object || Array.isArray(v)) visit(v, path + '.' + k, depth+1); } catch(e){}
          }
        }
      }
      visit(window, 'window', 0);
      return out;
    })()""")
    print("live WebSockets found:", json.dumps(found, indent=1)[:1200])

    # 2) hook WebSocket constructor + record frames on any NEW socket
    c.evaluate("""(() => {
      if (window.__ws_hooked) return 'already';
      window.__ws_hooked = true;
      window.__ws_log = [];
      const RealWS = window.WebSocket;
      function HookedWS(url, protocols) {
        const rec = {url: String(url), protocols: protocols ? String(protocols) : null,
                     sent: [], received: [], at: Date.now()};
        window.__ws_log.push(rec);
        const ws = (protocols !== undefined) ? new RealWS(url, protocols) : new RealWS(url);
        ws.addEventListener('open', () => { rec.openAt = Date.now(); });
        const origSend = ws.send.bind(ws);
        ws.send = function(data) {
          try { rec.sent.push(typeof data === 'string' ? data : '<binary ' + (data.byteLength||data.length||'?') + '>'); } catch(e){}
          return origSend(data);
        };
        ws.addEventListener('message', (ev) => {
          try { rec.received.push(typeof ev.data === 'string' ? ev.data.slice(0,300) : '<binary>'); } catch(e){}
        });
        return ws;
      }
      HookedWS.prototype = RealWS.prototype;
      for (const k of ['CONNECTING','OPEN','CLOSING','CLOSED']) HookedWS[k] = RealWS[k];
      window.WebSocket = HookedWS;
      return 'hooked';
    })()""")

    # 3) close the live socket(s) to force reconnect
    closed = c.evaluate("""(() => {
      const seen = new Set(); let n = 0;
      function visit(obj, depth) {
        if (!obj || depth > 3 || seen.has(obj)) return;
        try { seen.add(obj); } catch(e){ return; }
        for (const k of Object.getOwnPropertyNames(obj)) {
          let v; try { v = obj[k]; } catch(e){ continue; }
          if (v instanceof WebSocket) { try { v.close(); n++; } catch(e){} }
          else if (v && typeof v === 'object' && depth < 3 && !(v instanceof Element) && !(v instanceof Window)) {
            try { if (v.constructor === Object || Array.isArray(v)) visit(v, depth+1); } catch(e){}
          }
        }
      }
      visit(window, 0);
      return n;
    })()""")
    print("closed live sockets:", closed)

    # 4) watch for the reconnect via CDP Network events
    ws_events = []
    end = time.monotonic() + 20
    while time.monotonic() < end:
        c.pump(0.6)
        for ev in list(c.events):
            m = ev.get("method") or ""
            if m.startswith("Network.webSocket"):
                ws_events.append(ev)
        c.events.clear()
        got = c.evaluate("(window.__ws_log||[]).length")
        if got and time.monotonic() > end - 12:
            break

    print("\nCDP ws events:", len(ws_events))
    for ev in ws_events:
        m = ev.get("method"); p = ev.get("params") or {}
        if m == "Network.webSocketCreated":
            print("CREATED:", p.get("url"))
        elif m == "Network.webSocketWillSendHandshakeRequest":
            req = p.get("request") or {}
            print("HANDSHAKE url:", req.get("url"))
            for k, v in (req.get("headers") or {}).items():
                print("   %s: %s" % (k, ("<%d chars>" % len(v)) if k.lower()=="cookie" else str(v)[:150]))
        elif m == "Network.webSocketHandshakeResponseReceived":
            r = p.get("response") or {}
            print("HANDSHAKE RESP:", r.get("status"), "| protocol:", r.get("headers",{}).get("sec-websocket-protocol"))
        elif m in ("Network.webSocketFrameSent","Network.webSocketFrameReceived"):
            pl = str((p.get("response") or {}).get("payloadData") or "")
            print("  %s len=%d head=%s" % (m.split("webSocketFrame")[1], len(pl), pl[:60]))

    log = c.evaluate("window.__ws_log || []")
    print("\npage-side ws_log:", json.dumps(log, indent=1)[:2000])
    pathlib.Path("state/meta_ws_open_sequence.json").write_text(
        json.dumps({"cdp_events": [{"m": e.get("method"), "p": e.get("params")} for e in ws_events],
                    "page_log": log}, indent=1)[:300000], encoding="utf-8")
    print("saved -> state/meta_ws_open_sequence.json")
finally:
    c.close()
