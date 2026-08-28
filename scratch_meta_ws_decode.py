"""P2: capture the FULL meta.ai websocket sent frame (untruncated), save it, and decode the
base64 protobuf envelope to assess replay feasibility. One sentinel send in the seat tab.
"""
import io, json, sys, time, pathlib, base64, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path("scripts/automation").resolve()))
from capture_sessions_cdp import CDP, targets, SENTINEL

tabs = [t for t in targets(9222) if "meta.ai" in (t.get("url") or "")]
t = tabs[0]
print("tab:", t.get("url")[:100])
c = CDP(t["webSocketDebuggerUrl"])
sent_frames, recv_frames, ws_urls = [], [], []
try:
    c.call("Page.bringToFront", timeout=12); time.sleep(1.2)
    c.call("Runtime.enable", timeout=25); c.call("Page.enable")
    c.call("Network.enable")

    # focus the visible contenteditable and type
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

    handled=set()
    def drain():
        for ev in list(c.events):
            m=ev.get("method"); p=ev.get("params") or {}
            if m=="Network.webSocketCreated":
                ws_urls.append(p.get("url"))
            elif m=="Network.webSocketFrameSent":
                pl=str((p.get("response") or {}).get("payloadData") or "")
                if pl and pl not in sent_frames: sent_frames.append(pl)
            elif m=="Network.webSocketFrameReceived":
                pl=str((p.get("response") or {}).get("payloadData") or "")
                if pl: recv_frames.append(pl)

    def key(k,code,vk,text=None):
        base={"key":k,"code":code,"windowsVirtualKeyCode":vk,"nativeVirtualKeyCode":vk}
        d=dict(base,type="keyDown")
        if text: d["text"]=text; d["unmodifiedText"]=text
        c.call("Input.dispatchKeyEvent",d,timeout=8)
        c.call("Input.dispatchKeyEvent",dict(base,type="keyUp"),timeout=8)
    key("Enter","Enter",13,"\r")
    end=time.monotonic()+10
    while time.monotonic()<end:
        c.pump(0.7); drain()

    print("ws urls created:", ws_urls)
    print("unique sent frames:", len(sent_frames), "| recv frames:", len(recv_frames))
    out = pathlib.Path("state/meta_ws_frames.json")
    out.write_text(json.dumps({"ws_urls":ws_urls,"sent":sent_frames,"recv":recv_frames[:30]},indent=1),encoding="utf-8")
    print("saved ->", out)

    # decode the first sent frame
    if sent_frames:
        raw = base64.b64decode(sent_frames[0])
        print("\n--- sent frame[0]: %d bytes raw ---" % len(raw))
        print("hex head:", raw[:24].hex())
        # the envelope appears to contain JSON with req-id + payload
        txt = raw.decode("utf-8","replace")
        # find JSON object
        i = txt.find("{")
        if i>=0:
            # try to parse the embedded JSON
            depth=0; j=i
            for j in range(i,len(txt)):
                if txt[j]=="{": depth+=1
                elif txt[j]=="}":
                    depth-=1
                    if depth==0: break
            js = txt[i:j+1]
            try:
                d=json.loads(js)
                print("embedded JSON keys:", sorted(d.keys()))
                print("req-id:", d.get("req-id"))
                pl = d.get("payload") or ""
                print("payload b64 len:", len(pl))
                inner = base64.b64decode(pl)
                print("payload decoded: %d bytes" % len(inner))
                itxt = inner.decode("utf-8","replace")
                # print printable runs
                import re
                runs = re.findall(r"[\x20-\x7e]{6,}", itxt)
                print("printable runs in payload:")
                for r in runs[:40]: print("   ", r[:120])
                pathlib.Path("state/meta_ws_payload.bin").write_bytes(inner)
            except Exception as e:
                print("embedded JSON parse failed:", e, "| head:", js[:200])
finally:
    c.close()
