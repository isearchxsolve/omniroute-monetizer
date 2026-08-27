import json, sys, time
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

URL_SUBSTR = "/api/"
captured = []

with Page("chat.cerebras.ai", port=9222) as p:
    # 1. Dismiss ALL consent buttons until none remain
    for _ in range(4):
        r = p.evaluate("""(()=>{
            const btn=[...document.querySelectorAll('button')]
                .find(b=>/^(Reject All|Accept All|Close|Confirm Preferences)$/i.test((b.textContent||'').trim()));
            if(btn){btn.click(); return btn.textContent.trim();}
            return null;
        })()""")
        if not r:
            break
        print("dismissed:", r)
        time.sleep(0.7)

    p.send("Network.enable")
    # 2. Type + Enter via CDP Input for realism
    p.evaluate("""(()=>{const ta=document.querySelector('textarea');
        if(ta){ta.focus(); ta.value='Reply exactly one word: Omni.';
        ta.dispatchEvent(new Event('input',{bubbles:true}));} return !!ta;})()""")
    time.sleep(0.4)
    # Use CDP Input.dispatchKeyEvent for Enter (more real than synthetic)
    p.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter",
                                      "code": "Enter", "windowsVirtualKeyCode": 13})
    p.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter",
                                      "code": "Enter", "windowsVirtualKeyCode": 13})

    deadline = time.time() + 25
    while time.time() < deadline:
        p.ws.settimeout(max(1.0, deadline - time.time()))
        try:
            msg = json.loads(p.ws.recv())
        except Exception:
            break
        m = msg.get("method", "")
        if m == "Network.requestWillBeSent":
            req = msg["params"].get("request", {})
            if URL_SUBSTR in req.get("url", "") and req.get("method") == "POST":
                captured.append({"url": req.get("url"), "method": req.get("method"),
                                 "headers": req.get("headers", {}),
                                 "postData": req.get("postData", ""),
                                 "requestId": msg["params"].get("requestId")})
        elif m == "Network.requestWillBeSentExtraInfo" and captured:
            rid = msg["params"].get("requestId")
            for c in captured:
                if c.get("requestId") == rid and "extra" not in c:
                    c["extra"] = msg["params"].get("headers", {})
        if captured and all("extra" in c for c in captured):
            time.sleep(1)  # small grace
            break

print(f"\nCAPTURED {len(captured)} POST request(s):")
for c in captured:
    print(f"\n  URL: {c['url']}")
    print(f"  postData: {repr(c.get('postData','')[:500])}")
    print("  --- wire headers ---")
    for k, v in (c.get("extra") or c.get("headers") or {}).items():
        if k.startswith(":"):
            continue
        print(f"    {k}: {str(v)[:110]}")

out = Path(r"d:\omniroute-monetizer\state\secrets\cerebras_ui_wire_capture.json")
out.write_text(json.dumps(captured, indent=1), encoding="utf-8")
print(f"\nSaved -> {out}")
