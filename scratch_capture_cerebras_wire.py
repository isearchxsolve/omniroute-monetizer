"""Capture the EXACT request the live cerebras page sends to /api/chat/completions.

Attaches to the live tab, enables Network, fires an in-page fetch (so the page's
own code adds whatever CSRF/headers it needs), and records the request headers +
body Chrome actually put on the wire via Network.requestWillBeSent(+ExtraInfo).
This is CAPTURE (Law 4), not runtime -- we record bytes, then replay statelessly.
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from cdp import Page

MATCH = "chat.cerebras.ai"
URL_SUBSTR = "/api/chat/completions"

captured = {}

with Page(MATCH, port=9222) as p:
    p.send("Network.enable")
    # collect events while we trigger
    import websocket
    # Trigger an in-page fetch with a minimal body. Use the page's own fetch so
    # credentials/cookies are attached by the browser exactly as a real call.
    js = """
    (async () => {
      const body = {messages:[{role:'user',content:'Reply exactly one word: Omni.'}],
                    model:'gemma-4-31b', stream:false, temperature:0.7, top_p:0.9};
      try {
        const r = await fetch('/api/chat/completions', {
          method:'POST', credentials:'include',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify(body)});
        const text = await r.text();
        return JSON.stringify({status:r.status, body:text.slice(0,400)});
      } catch(e) { return 'FETCH_ERR '+e; }
    })()
    """
    # We need to pump events to catch requestWillBeSent before/while evaluating.
    # Send evaluate asynchronously by using a thread-free approach: send the eval,
    # then drain messages collecting Network events + the eval result.
    p._id += 1
    eval_id = p._id
    p.ws.send(json.dumps({"id": eval_id, "method": "Runtime.evaluate",
                          "params": {"expression": js, "awaitPromise": True,
                                     "returnByValue": True, "userGesture": True}}))
    deadline = time.time() + 30
    eval_result = None
    while time.time() < deadline:
        p.ws.settimeout(max(1.0, deadline - time.time()))
        try:
            msg = json.loads(p.ws.recv())
        except Exception:
            break
        m = msg.get("method", "")
        if m == "Network.requestWillBeSent":
            req = msg["params"].get("request", {})
            if URL_SUBSTR in req.get("url", ""):
                captured["url"] = req.get("url")
                captured["method"] = req.get("method")
                captured["headers"] = req.get("headers", {})
                captured["postData"] = req.get("postData", "")
                captured["requestId"] = msg["params"].get("requestId")
        elif m == "Network.requestWillBeSentExtraInfo":
            if captured and msg["params"].get("requestId") == captured.get("requestId"):
                captured["extra_headers"] = msg["params"].get("headers", {})
        elif msg.get("id") == eval_id:
            eval_result = msg.get("result", {}).get("result", {}).get("value")
            # keep draining a moment for extra info
            if captured.get("extra_headers"):
                break

print("IN-PAGE FETCH RESULT:", eval_result)
print("\nCAPTURED WIRE REQUEST:")
print("  url:", captured.get("url"))
print("  method:", captured.get("method"))
print("  postData:", repr(captured.get("postData", "")[:200]))
print("  --- headers (requestWillBeSent) ---")
for k, v in (captured.get("headers") or {}).items():
    print(f"    {k}: {str(v)[:90]}")
print("  --- extra headers (wire) ---")
for k, v in (captured.get("extra_headers") or {}).items():
    print(f"    {k}: {str(v)[:90]}")

out = Path(r"d:\omniroute-monetizer\state\secrets\cerebras_wire_capture.json")
out.write_text(json.dumps(captured, indent=1), encoding="utf-8")
print(f"\nSaved -> {out}")
