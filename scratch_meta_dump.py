"""scratch_meta_dump.py — dump ALL ws frames sent + POST bodies for meta.ai to find the encoding."""
import sys, time, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import (CDP, CDPError, JS_FOCUS_COMPOSER, JS_READ_ACTIVE, JS_SEND,
                                  SENTINEL, targets)

PORT = 9222
tabs = [t for t in targets(PORT) if "www.meta.ai" in (t.get("url") or "").lower()]
if not tabs:
    print("NO TAB"); sys.exit(1)
t = tabs[0]
print("tab:", t.get("url"))
c = CDP(t["webSocketDebuggerUrl"], timeout=120)
c.call("Runtime.enable", timeout=25)
c.call("Page.enable")
c.call("Network.enable")
c.call("Page.reload", {"ignoreCache": False})

# wait for composer
deadline = time.monotonic() + 45
focus = {}
while time.monotonic() < deadline:
    if (c.evaluate("document.readyState") or "") == "complete":
        focus = c.evaluate(JS_FOCUS_COMPOSER) or {}
        if focus.get("ok"):
            break
    time.sleep(1.5)
print("composer:", focus)
if not focus.get("ok"):
    print("NO COMPOSER"); sys.exit(1)

c.call("Input.insertText", {"text": SENTINEL})
time.sleep(0.4)
back = c.evaluate(JS_READ_ACTIVE) or {}
print("landed:", SENTINEL.split(":")[0] in (back.get("text") or ""), repr((back.get("text") or "")[:80]))

ws_sent = []
ws_recv = []
posts = []
handled = set()

def drain(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        c.pump(0.8)
        for ev in list(c.events):
            m = ev.get("method"); p = ev.get("params") or {}
            if m == "Network.webSocketFrameSent":
                ws_sent.append(str((p.get("response") or {}).get("payloadData") or ""))
            elif m == "Network.webSocketFrameReceived":
                ws_recv.append(str((p.get("response") or {}).get("payloadData") or ""))
            elif m == "Network.requestWillBeSent":
                rid = str(p.get("requestId") or "")
                if not rid or rid in handled: continue
                handled.add(rid)
                req = p.get("request") or {}
                if req.get("method") in ("POST", "PUT", "PATCH"):
                    body = req.get("postData") or ""
                    if not body and req.get("hasPostData"):
                        try:
                            body = (c.call("Network.getRequestPostData", {"requestId": rid}, timeout=10).get("postData") or "")
                        except CDPError:
                            body = "<no-body>"
                    posts.append({"url": req.get("url",""), "body": body})
        c.events.clear()

drain(5.0)
# submit via js click (Enter dispatch can time out on meta.ai)
try:
    c.call("Input.dispatchKeyEvent", {"type":"keyDown","key":"Enter","code":"Enter","windowsVirtualKeyCode":13,"nativeVirtualKeyCode":13,"text":"\r"}, timeout=8)
    c.call("Input.dispatchKeyEvent", {"type":"keyUp","key":"Enter","code":"Enter","windowsVirtualKeyCode":13,"nativeVirtualKeyCode":13}, timeout=8)
    drain(6.0)
except CDPError as e:
    print("enter skipped:", e)
r = c.evaluate(JS_SEND.replace("__CLICK__", "true")) or {}
print("js_click:", r.get("ok"), r.get("label"), r.get("error"))
drain(12.0)

print(f"\n=== WS SENT: {len(ws_sent)} ===")
for i, f in enumerate(ws_sent):
    print(f"[{i}] len={len(f)} {f[:300]!r}")
print(f"\n=== WS RECV: {len(ws_recv)} ===")
for i, f in enumerate(ws_recv[:20]):
    print(f"[{i}] len={len(f)} {f[:200]!r}")
print(f"\n=== POSTS: {len(posts)} ===")
for i, p in enumerate(posts):
    print(f"[{i}] {p['url'][:110]}")
    print(f"     body len={len(p['body'])} {p['body'][:300]!r}")
