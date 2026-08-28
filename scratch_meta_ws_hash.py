"""P2: (a) find meta.ai's websocket URL + auth, (b) send a 2nd sentinel and compare the SHA-256
hash field against the first capture to classify it static-vs-per-message. Read-only on state.
"""
import io, json, sys, time, pathlib, base64, re, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets, SENTINEL

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
c = CDP(t["webSocketDebuggerUrl"])
sent = []
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(1.2)
    c.call("Runtime.enable", timeout=25); c.call("Page.enable")

    # (a) find ws url from resource timing + any global socket refs
    wsinfo = c.evaluate("""(() => {
      const res = performance.getEntriesByType('resource')
        .filter(r => /ws|socket|mqtt|abracadabra|kadabra/i.test(r.name))
        .map(r => r.name);
      return {resourceWs: res.slice(-8)};
    })()""")
    print("resource ws-like entries:", json.dumps(wsinfo, indent=1)[:600])

    c.call("Network.enable")
    # also catch the ws url if it reconnects
    ws_urls = []
    def drain():
        for ev in list(c.events):
            m=ev.get("method"); p=ev.get("params") or {}
            if m=="Network.webSocketCreated": ws_urls.append(p.get("url"))
            elif m=="Network.webSocketFrameSent":
                pl=str((p.get("response") or {}).get("payloadData") or "")
                if pl and pl not in sent: sent.append(pl)

    # focus + type + send
    focus = c.evaluate("""(() => {
      const aes=[...document.querySelectorAll('[contenteditable="true"], textarea')];
      const e=aes.find(x=>x.offsetParent)||aes[0]; if(!e) return {ok:false};
      e.focus(); const r=e.getBoundingClientRect();
      return {ok:true,x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};
    })()""")
    if focus.get("x"):
        for k in ("mousePressed","mouseReleased"):
            c.call("Input.dispatchMouseEvent",{"type":k,"x":focus["x"],"y":focus["y"],"button":"left","clickCount":1})
        time.sleep(0.3)
    c.call("Input.insertText",{"text":SENTINEL})
    time.sleep(0.3)
    def key(k,code,vk,text=None):
        base={"key":k,"code":code,"windowsVirtualKeyCode":vk,"nativeVirtualKeyCode":vk}
        d=dict(base,type="keyDown")
        if text: d["text"]=text; d["unmodifiedText"]=text
        c.call("Input.dispatchKeyEvent",d,timeout=8)
        c.call("Input.dispatchKeyEvent",dict(base,type="keyUp"),timeout=8)
    key("Enter","Enter",13,"\r")
    end=time.monotonic()+8
    while time.monotonic()<end:
        c.pump(0.7); drain()

    print("ws urls seen this run:", ws_urls)

    def extract_hash(frame_b64):
        try:
            raw = base64.b64decode(frame_b64)
            txt = raw.decode("utf-8","replace")
            i = txt.find("{")
            depth=0
            for j in range(i,len(txt)):
                if txt[j]=="{": depth+=1
                elif txt[j]=="}":
                    depth-=1
                    if depth==0: break
            d=json.loads(txt[i:j+1])
            inner = base64.b64decode(d.get("payload") or "")
            itxt = inner.decode("utf-8","replace")
            m = re.search(r"@([0-9a-f]{64})", itxt)
            # also grab req-id and prompt presence
            return {"hash": m.group(1) if m else None,
                    "req_id": d.get("req-id"),
                    "has_prompt": SENTINEL in itxt}
        except Exception as e:
            return {"error": str(e)[:80]}

    if sent:
        info2 = extract_hash(sent[0])
        print("\n2nd-send frame:", json.dumps(info2, indent=1))
        # compare with 1st capture
        prev = json.loads(pathlib.Path("state/meta_ws_frames.json").read_text(encoding="utf-8"))
        if prev.get("sent"):
            info1 = extract_hash(prev["sent"][0])
            print("1st-send frame:", json.dumps(info1, indent=1))
            if info1.get("hash") and info2.get("hash"):
                print("\nHASH STABILITY:", "STATIC (same)" if info1["hash"]==info2["hash"] else "PER-MESSAGE (differs)")
    else:
        print("no sent frame captured this run")
finally:
    c.close()
