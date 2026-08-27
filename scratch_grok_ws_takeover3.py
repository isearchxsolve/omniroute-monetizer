"""scratch_grok_ws_takeover3.py — CLOSE the grok tab, wait out the server grace period, then own the socket.

Hypothesis: grok keys the realtime session by account cookie (one active mgw socket per account).
When Chrome's socket dies, the server keeps the session 'alive' for a heartbeat grace period
(~30-60s) before accepting a new owner. Test: close tab, wait 45s, connect fresh conversation.
"""
import sys, json, time, uuid, pathlib, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import websocket as wsc

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import targets

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
cookie = d["cookie_header"]
create_frame = json.loads(d["recorded_ws"]["frames_sent"][0])
model = create_frame["event"]["session"]["model"]
caps = create_frame["event"]["session"]["x_grok"].get("protocol_capabilities", [])

PORT = 9222
tabs = [t for t in targets(PORT) if "grok.com" in (t.get("url") or "")]
if tabs:
    tab = tabs[0]
    tid = tab.get("id")
    # close the tab via the browser-level CDP endpoint
    browser_ws = None
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=5) as r:
        browser_ws = json.loads(r.read().decode()).get("webSocketDebuggerUrl")
    import websocket as w2
    bw = w2.create_connection(browser_ws, timeout=10)
    bw.send(json.dumps({"id": 1, "method": "Target.closeTarget", "params": {"targetId": tid}}))
    print("closeTarget resp:", bw.recv()[:120])
    bw.close()
    print("closed grok tab", tid)
else:
    print("no grok tab (already closed)")

WAIT = 45
print(f"waiting {WAIT}s for server grace period...")
time.sleep(WAIT)

ws_url = f"wss://grok.com/ws/mgw/?uid={uuid.uuid4()}"
ws = wsc.create_connection(ws_url, timeout=30, suppress_origin=True, max_size=64*1024*1024,
                           header=["Cookie: " + cookie, "Origin: https://grok.com",
                                   "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                                              "Chrome/151.0.0.0 Safari/537.36"])
def send(o): ws.send(json.dumps(o))
def recv(t=10):
    ws.settimeout(t)
    try: return json.loads(ws.recv())
    except Exception as e: return {"__error__": f"{type(e).__name__}: {e}"}

conv = str(uuid.uuid4())
send({"session_id": conv, "event": {"type": "session.create",
      "event_id": f"evt_init_{uuid.uuid4()}",
      "session": {"model": model, "x_grok": {"protocol_capabilities": caps,
                  "conversation_id": conv, "load_existing": False, "use_chunk": True,
                  "enable_side_by_side": True, "force_side_by_side": False,
                  "enable_image_generation": True, "image_generation_count": 2,
                  "disable_text_follow_ups": False, "disable_artifact": True,
                  "force_concise": False}}}})
created = False
end = time.monotonic() + 15
while time.monotonic() < end:
    m = recv(5)
    if "__error__" in m: print("err:", m["__error__"]); break
    typ = (m.get("event") or {}).get("type")
    print("event:", typ)
    if typ == "session.created": created = True; break
    if typ in ("session.moved", "error"):
        if typ == "error": print(json.dumps(m)[:300])
        break
print("BECAME OWNER:", created)

answer = ""
if created:
    send({"session_id": conv, "event": {"type": "response.create",
          "event_id": f"evt_resp_{int(time.time()*1000)}",
          "item": {"type": "message", "role": "user",
                   "x_grok": {"client_message_id": str(uuid.uuid4()),
                              "input_chunks": [{"text": {"text": "Reply exactly one word: Omni."}}]}},
          "parent_response_id": None}})
    parts = []; done = False
    end = time.monotonic() + 90
    while time.monotonic() < end and not done:
        m = recv(10)
        if "__error__" in m: print("err:", m["__error__"]); break
        ev = m.get("event") or {}; typ = ev.get("type")
        if typ == "response.output_text.delta": parts.append(ev.get("delta") or "")
        elif typ in ("response.output_item.done", "conversation.history.item"):
            item = ev.get("item") or {}
            if item.get("role") == "assistant":
                for ch in (item.get("x_grok") or {}).get("output_chunks", []):
                    tx = ch.get("text") or {}
                    if tx.get("channel") == "CHANNEL_ASSISTANT_RESPONSE" and tx.get("text"):
                        parts = [tx["text"]]
        elif typ == "response.done": done = True
        elif typ == "error": print("ERROR", json.dumps(ev)[:300]); break
    answer = "".join(parts).strip()
    print(f"ANSWER: {answer!r}")
ws.close()
print("RESULT:", "LIVE" if answer else "EMPTY/NO-OWNER")
