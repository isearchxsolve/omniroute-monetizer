"""P2 diagnostic: where does meta.ai actually send? Attach to the seat tab on 9222, enable
Network, type the sentinel, submit, and dump every POST url + ws frame payload (truncated).
Read-only w.r.t. our state; sends one sentinel message in the seat's own tab (its designed use).
No cookies/secrets printed.
"""
import io, json, sys, time, pathlib, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))

from capture_sessions_cdp import CDP, targets, SENTINEL, SENTINEL_FORMS, has_sentinel, reg, host_of

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
if not tabs:
    print("NO meta.ai tab on 9222"); raise SystemExit(1)
t = tabs[0]
print("tab:", t.get("url")[:100])

c = CDP(t["webSocketDebuggerUrl"])
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(1.5)
    c.call("Runtime.enable", timeout=25)
    c.call("Page.enable")

    # what does the page look like? composer state
    info = c.evaluate("""(() => {
      const aes = [...document.querySelectorAll('[contenteditable="true"], textarea, input[type="text"]')];
      const active = document.activeElement;
      return {
        title: document.title,
        url: location.href,
        editors: aes.map(e => ({tag: e.tagName, cls: (e.className||'').toString().slice(0,60),
                                 ph: e.getAttribute('placeholder')||e.getAttribute('aria-label')||'',
                                 vis: !!(e.offsetParent)})),
        activeTag: active ? active.tagName : null,
        bodyTextTail: document.body.innerText.slice(-300)
      };
    })()""")
    print("page info:", json.dumps(info, indent=1)[:1200])

    c.call("Network.enable")

    # focus first visible editor and type
    focus = c.evaluate("""(() => {
      const aes = [...document.querySelectorAll('[contenteditable="true"], textarea')];
      const e = aes.find(x => x.offsetParent) || aes[0];
      if (!e) return {ok:false, error:'no editor'};
      e.focus();
      const r = e.getBoundingClientRect();
      return {ok:true, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
              tag: e.tagName, ph: e.getAttribute('placeholder')||e.getAttribute('aria-label')||''};
    })()""")
    print("focus:", focus)
    if focus.get("x"):
        for kind in ("mousePressed", "mouseReleased"):
            c.call("Input.dispatchMouseEvent", {"type": kind, "x": focus["x"], "y": focus["y"],
                                                "button": "left", "clickCount": 1})
        time.sleep(0.3)
    c.call("Input.insertText", {"text": SENTINEL})
    back = c.evaluate("(() => { const a=document.activeElement; return {text: a ? (a.value||a.textContent||'').slice(0,80) : null}; })()")
    print("typed, active element now:", back)

    posts, wss, others = [], [], []
    handled = set()

    def drain():
        for ev in list(c.events):
            m = ev.get("method"); p = ev.get("params") or {}
            if m == "Network.requestWillBeSent":
                rid = str(p.get("requestId") or "")
                if rid in handled: continue
                handled.add(rid)
                req = p.get("request") or {}
                url = req.get("url") or ""
                meth = req.get("method")
                body = req.get("postData") or ""
                if not body and req.get("hasPostData"):
                    try: body = c.call("Network.getRequestPostData", {"requestId": rid}, timeout=8).get("postData") or ""
                    except Exception: body = "<unfetchable>"
                row = (meth, url[:130], len(body), has_sentinel(body), body[:180].replace("\n", " "))
                if meth in ("POST", "PUT", "PATCH"): posts.append(row)
                else: others.append((meth, url[:110]))
            elif m in ("Network.webSocketFrameSent", "Network.webSocketFrameReceived"):
                pl = str((p.get("response") or {}).get("payloadData") or "")
                wss.append((m.split("webSocketFrame")[1], len(pl), has_sentinel(pl), pl[:160].replace("\n", " ")))
            elif m == "Network.webSocketCreated":
                wss.append(("CREATED", 0, False, str(p.get("url"))[:160]))

    # submit: Enter
    def key(k, code, vk, text=None):
        base = {"key": k, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
        d = dict(base, type="keyDown")
        if text: d["text"] = text; d["unmodifiedText"] = text
        c.call("Input.dispatchKeyEvent", d, timeout=8)
        c.call("Input.dispatchKeyEvent", dict(base, type="keyUp"), timeout=8)
    key("Enter", "Enter", 13, "\r")
    print("-- Enter pressed, watching 12s --")
    end = time.monotonic() + 12
    while time.monotonic() < end:
        c.pump(0.8); drain()

    print("\nPOST/PUT/PATCH (%d):" % len(posts))
    for meth, url, blen, hit, head in posts:
        print("  %s %s body=%dB sentinel=%s" % (meth, url, blen, hit))
        if hit or blen < 400: print("      head:", head)
    print("\nWS events (%d):" % len(wss))
    for kind, ln, hit, head in wss[:40]:
        print("  %s len=%d sentinel=%s | %s" % (kind, ln, hit, head))
    print("\nother requests:", len(others))
    for meth, url in others[:15]: print("  %s %s" % (meth, url))
finally:
    c.close()
