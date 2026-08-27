"""Observe DeepSeek's live PoW sequence in the browser: requests AND response bodies.

The browser solves the PoW on every send. We attach via CDP, enable Network with
response-body capture, type the sentinel, submit, and record every request/response
on the chat.deepseek.com API. What you see is what you get.
"""
import base64, json, time, io, sys, websocket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WS = "ws://127.0.0.1:9222/devtools/page/8494E78FCFFAEFBE7E563EB6DDEE5DB8"
SENTINEL = "Reply with only the number: 41 + 17"

ws = websocket.create_connection(WS, suppress_origin=True, timeout=10)
_id = 0
def send(method, params=None):
    global _id
    _id += 1
    ws.send(json.dumps({"id": _id, "method": method, "params": params or {}}))
    return _id

def recv_until(pred, deadline):
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            break
        if pred(msg):
            return msg
    return None

send("Network.enable")
send("Runtime.enable")
time.sleep(0.5)

# Type the sentinel into the composer and submit with Enter
send("Runtime.evaluate", {"expression": """
(() => {
  const ta = document.querySelector('textarea, div[contenteditable="true"], [role="textbox"]');
  if (!ta) return 'NO_COMPOSER';
  ta.focus();
  return 'FOCUSED:' + ta.tagName;
})()
"""})
time.sleep(0.3)
send("Input.insertText", {"text": SENTINEL})
time.sleep(0.3)
send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter",
                                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13, "text": "\r"})
send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter",
                                "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})

# Collect network events for ~25s
requests_seen = {}   # requestId -> {url, method, headers, postData}
responses_seen = {}  # requestId -> {status, mimeType}
bodies = {}          # requestId -> body text
deadline = time.time() + 25
pending_body = []    # requestIds awaiting GetResponseBody

while time.time() < deadline:
    try:
        ws.settimeout(max(0.2, deadline - time.time()))
        msg = json.loads(ws.recv())
    except Exception:
        continue
    m = msg.get("method", "")
    p = msg.get("params", {})
    if m == "Network.requestWillBeSent":
        req = p.get("request", {})
        url = req.get("url", "")
        if "deepseek.com" in url and "/api/" in url:
            rid = p.get("requestId")
            requests_seen[rid] = {
                "url": url, "method": req.get("method"),
                "headers": req.get("headers", {}),
                "postData": req.get("postData", ""),
            }
            print(f"\n>>> REQ {req.get('method')} {url}")
            for hk in ("x-ds-pow-response", "authorization", "x-ds-challenge"):
                if hk in {k.lower() for k in req.get("headers", {})}:
                    hv = next(v for k, v in req["headers"].items() if k.lower() == hk)
                    print(f"    {hk}: {hv[:120]}")
            if req.get("postData"):
                print(f"    body: {req['postData'][:200]}")
    elif m == "Network.responseReceived":
        rid = p.get("requestId")
        if rid in requests_seen:
            resp = p.get("response", {})
            responses_seen[rid] = {"status": resp.get("status"), "mimeType": resp.get("mimeType")}
            pending_body.append(rid)
            print(f"<<< RESP {resp.get('status')} {resp.get('mimeType')} {requests_seen[rid]['url'][:80]}")
    elif m == "Network.loadingFinished":
        rid = p.get("requestId")
        if rid in pending_body:
            pending_body.remove(rid)
            bid = send("Network.getResponseBody", {"requestId": rid})
            # read the result
            rmsg = recv_until(lambda x: x.get("id") == bid, time.time() + 3)
            if rmsg and rmsg.get("result", {}).get("body"):
                bodies[rid] = rmsg["result"]["body"]
                print(f"    BODY[{len(bodies[rid])}B]: {bodies[rid][:300]}")

ws.close()

# Dump everything
out = {"requests": requests_seen, "responses": responses_seen, "bodies": bodies}
with open("_ds_live_sequence.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1, ensure_ascii=False)
print(f"\n\nSAVED _ds_live_sequence.json: {len(requests_seen)} requests, {len(bodies)} bodies")
