"""Capture cerebras's REAL UI send: type into the composer, click send, record the
wire request via Network.requestWillBeSent(+ExtraInfo). This is what the app truly
posts (headers, body, endpoint) -- the ground truth a plain fetch can't reproduce.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

URL_SUBSTR = "/api/"
captured = []

with Page("chat.cerebras.ai", port=9222) as p:
    p.send("Network.enable")
    # Find the composer + send button
    probe = p.evaluate("""(()=>{
        const ta=document.querySelector('textarea, [contenteditable="true"], div[role="textbox"]');
        const btns=[...document.querySelectorAll('button')].map(b=>(b.textContent||'').trim()).filter(Boolean);
        return JSON.stringify({hasComposer:!!ta, composerTag:ta?ta.tagName:null,
                               buttons:btns.slice(0,30)});
    })()""")
    print("probe:", probe)

    # Type into composer
    p.evaluate("""(()=>{
        const ta=document.querySelector('textarea, [contenteditable="true"], div[role="textbox"]');
        if(!ta) return 'no composer';
        ta.focus();
        if(ta.tagName==='TEXTAREA'){ ta.value='Reply exactly one word: Omni.';
            ta.dispatchEvent(new Event('input',{bubbles:true}));
        } else { ta.textContent='Reply exactly one word: Omni.';
            ta.dispatchEvent(new Event('input',{bubbles:true})); }
        return 'typed';
    })()""")
    time.sleep(0.5)

    # Start async eval to click send, then drain network events
    p._id += 1
    eval_id = p._id
    p.ws.send(json.dumps({"id": eval_id, "method": "Runtime.evaluate",
                          "params": {"expression": """(()=>{
                const btn=[...document.querySelectorAll('button')]
                    .find(b=>/send|submit|arrow|\\u2191/i.test((b.textContent||'')+(b.getAttribute('aria-label')||''))
                          || b.type==='submit');
                if(btn){btn.click(); return 'clicked '+(btn.textContent||btn.getAttribute('aria-label')||'').trim();}
                // fallback: Enter on composer
                const ta=document.querySelector('textarea, [contenteditable="true"]');
                if(ta){ta.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));return 'enter';}
                return 'no send control';})()""",
                                     "returnByValue": True, "userGesture": True}}))
    deadline = time.time() + 20
    click_result = None
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
        elif msg.get("id") == eval_id:
            click_result = msg.get("result", {}).get("result", {}).get("value")

print("click result:", click_result)
print(f"\nCAPTURED {len(captured)} POST request(s):")
for c in captured:
    print(f"\n  URL: {c['url']}")
    print(f"  postData: {repr(c.get('postData','')[:300])}")
    print("  --- wire headers ---")
    for k, v in (c.get("extra") or c.get("headers") or {}).items():
        if k.startswith(":"):
            continue
        print(f"    {k}: {str(v)[:100]}")

out = Path(r"d:\omniroute-monetizer\state\secrets\cerebras_ui_wire_capture.json")
out.write_text(json.dumps(captured, indent=1), encoding="utf-8")
print(f"\nSaved -> {out}")
