"""P2 build-step 3: the main-world heap has ZERO WebSocket instances, yet ws frames flow on this
page target. Find where the socket really lives: enumerate execution contexts (iframes/isolated
worlds), DOM iframes, and browser targets (workers) related to meta.ai; then queryObjects for
WebSocket instances in EVERY context.
"""
import io, json, sys, time, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
print("tab:", t.get("url"), "| id:", t.get("id"))
c = CDP(t["webSocketDebuggerUrl"])
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(0.5)
    c.call("Runtime.enable", timeout=25)
    time.sleep(1.0)

    # 1) execution contexts seen via events
    ctxs = []
    for ev in c.events:
        if ev.get("method") == "Runtime.executionContextCreated":
            ci = (ev.get("params") or {}).get("context") or {}
            ctxs.append({"id": ci.get("id"), "origin": ci.get("origin"),
                         "name": ci.get("name"), "auxData": ci.get("auxData")})
    print("execution contexts:", len(ctxs))
    for x in ctxs:
        print("  ctx", x["id"], "| origin:", x.get("origin"), "| name:", repr(x.get("name")),
              "| aux:", json.dumps(x.get("auxData") or {})[:100])

    # 2) DOM iframes
    iframes = c.evaluate("""(() => {
        const fs = [...document.querySelectorAll('iframe,frame')];
        return fs.map(f => ({src: f.src || '', id: f.id, name: f.name, vis: !!(f.offsetWidth||f.offsetHeight)}));
    })()""")
    print("\nDOM iframes:", json.dumps(iframes, indent=1)[:800])

    # 3) per-context WebSocket census via queryObjects
    for x in ctxs:
        cid = x["id"]
        try:
            proto = c.call("Runtime.evaluate", {
                "expression": "WebSocket.prototype", "returnByValue": False,
                "contextId": cid})
            oid = (proto.get("result") or {}).get("objectId")
            if not oid:
                print("  ctx %s: no WebSocket.prototype" % cid); continue
            objs = c.call("Runtime.queryObjects", {"prototypeObjectId": oid})
            arr = (objs.get("objects") or {}).get("objectId")
            if not arr:
                print("  ctx %s: queryObjects empty" % cid); continue
            desc = c.call("Runtime.callFunctionOn", {
                "objectId": arr, "returnByValue": True,
                "functionDeclaration": """function() {
                    return this.map(ws => {
                        let u = '', rs = -1;
                        try { u = ws.url; } catch(e){}
                        try { rs = ws.readyState; } catch(e){}
                        return {url: u, readyState: rs};
                    });
                }"""})
            socks = (desc.get("result") or {}).get("value") or []
            print("  ctx %s: %d WebSocket instances" % (cid, len(socks)))
            for s in socks:
                print("      url:", s.get("url"), "| readyState:", s.get("readyState"))
        except Exception as e:
            print("  ctx %s: error %s" % (cid, str(e)[:100]))

    # 4) browser-wide targets related to meta.ai (workers, iframes)
    ver = json.loads(__import__("urllib.request", fromlist=["urlopen"]).urlopen(
        "http://127.0.0.1:9222/json/list", timeout=10).read())
    rel = [x for x in ver if "meta" in ((x.get("url") or "") + (x.get("title") or "")).lower()]
    print("\nbrowser targets mentioning meta:", len(rel))
    for x in rel:
        print("  type:", x.get("type"), "| url:", (x.get("url") or "")[:110],
              "| ws:", bool(x.get("webSocketDebuggerUrl")))
finally:
    c.close()
