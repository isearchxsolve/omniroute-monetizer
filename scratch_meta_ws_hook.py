"""P2: hook window.WebSocket BEFORE page load (addScriptToEvaluateOnNewDocument) to capture the
exact ws URL + any auth, then reload. Read-only on state.
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
    c.call("Page.enable")
    hook = """
    (() => {
      window.__ws_captures = [];
      const RealWS = window.WebSocket;
      function HookedWS(url, protocols) {
        try { window.__ws_captures.push({url: String(url), protocols: protocols ? String(protocols) : null, at: Date.now()}); } catch(e){}
        if (protocols !== undefined) return new RealWS(url, protocols);
        return new RealWS(url);
      }
      HookedWS.prototype = RealWS.prototype;
      HookedWS.CONNECTING = RealWS.CONNECTING; HookedWS.OPEN = RealWS.OPEN;
      HookedWS.CLOSING = RealWS.CLOSING; HookedWS.CLOSED = RealWS.CLOSED;
      window.WebSocket = HookedWS;
    })();
    """
    c.call("Page.addScriptToEvaluateOnNewDocument", {"source": hook})
    c.call("Page.reload", {"ignoreCache": False})
    time.sleep(12)
    caps = c.evaluate("window.__ws_captures || []")
    print("ws captures:", json.dumps(caps, indent=1)[:1500])
    # remove the hook so future loads are clean
    try:
        c.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": "1"})
    except Exception as e:
        print("hook removal note:", str(e)[:80])
finally:
    c.close()
