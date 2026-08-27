import json, sys, time
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

URL_SUBSTR = "/api/"
captured = []

with Page("chat.cerebras.ai", port=9222) as p:
    # 1. Dismiss consent overlay
    r = p.evaluate("""(()=>{
        const btn=[...document.querySelectorAll('button')]
            .find(b=>/^(Reject All|Accept All)$/i.test((b.textContent||'').trim()));
        if(btn){btn.click(); return 'dismissed: '+btn.textContent.trim();}
        return 'no consent button';
    })()""")
    print("consent:", r)
    time.sleep(1.0)

    p.send("Network.enable")
    # 2. Type into composer
    r = p.evaluate("""(()=>{
        const ta=document.querySelector('textarea');
        if(!ta) return 'no composer';
        ta.focus();
        ta.value='Reply exactly one word: Omni.';
        ta.dispatchEvent(new Event('input',{bubbles:true}));
        return 'typed';
    })()""")
    print("type:", r)
    time.sleep(0.5)

    # 3. Click the actual send button (exclude consent buttons)
    p._id += 1
    eval_id = p._id
    p.ws.send(json.dumps({"id": eval_id, "method": "Runtime.evaluate",
                          "params": {"expression": """(()=>{
                const skip=/Reject|Accept|Preference|Necessary|Performance|Personalization|Targeting|Confirm|Show more/i;
                const btns=[...document.querySelectorAll('button')].filter(b=>!skip.test((b.textContent||'')+(b.getAttribute('aria-label')||'')));
                const btn=btns.find(b=>/send|submit|\\u2191/i.test((b.textContent||'')+(b.getAttribute('aria-label')||''))||b.type==='submit')
                          || btns[btns.length-1];
                if(btn){btn.click(); return 'clicked: '+((btn.textContent||'').trim()||btn.getAttribute('aria-label')||'?');}
                return 'no button';})()""",
                                     "returnByValue": True, "userGesture": True}}))
    deadline = time.time() + 25
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
    print(f"  postData: {repr(c.get('postData','')[:400])}")
    print("  --- wire headers ---")
    for k, v in (c.get("extra") or c.get("headers") or {}).items():
        if k.startswith(":"):
            continue
        print(f"    {k}: {str(v)[:110]}")

out = Path(r"d:\omniroute-monetizer\state\secrets\cerebras_ui_wire_capture.json")
out.write_text(json.dumps(captured, indent=1), encoding="utf-8")
print(f"\nSaved -> {out}")
