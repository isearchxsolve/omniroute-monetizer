"""scratch_grok_ws_live.py — FULL grok websocket replay using Chrome's captured uid. PROOF.

Key discovery: the ws URL `uid` param is the device/session key. Reusing Chrome's captured uid
makes Python the same device -> session.created (owner). A fresh uid -> session.moved (evicted).
This script: connect with captured uid, fresh conversation, send sentinel, read the answer.
"""
import sys, json, time, uuid, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import websocket as wsc

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
cookie = d["cookie_header"]
create_frame = json.loads(d["recorded_ws"]["frames_sent"][0])
model = create_frame["event"]["session"]["model"]
caps = create_frame["event"]["session"]["x_grok"].get("protocol_capabilities", [])
captured_uid = d["recorded_ws"]["url"].split("uid=")[1]
print("using captured uid:", captured_uid)

ws_url = f"wss://grok.com/ws/mgw/?uid={captured_uid}"
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
print("OWNER:", created)
if not created:
    ws.close(); sys.exit(1)

PROMPT = "Reply exactly one word: Omni."
send({"session_id": conv, "event": {"type": "response.create",
      "event_id": f"evt_resp_{int(time.time()*1000)}",
      "item": {"type": "message", "role": "user",
               "x_grok": {"client_message_id": str(uuid.uuid4()),
                          "input_chunks": [{"text": {"text": PROMPT}}]}},
      "parent_response_id": None}})
print("sentinel sent")

parts = []; done = False; events = []
end = time.monotonic() + 90
while time.monotonic() < end and not done:
    m = recv(10)
    if "__error__" in m: print("err:", m["__error__"]); break
    ev = m.get("event") or {}; typ = ev.get("type")
    events.append(typ)
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
print("\nevents:", events[:50])
print(f"\nANSWER ({len(answer)} chars): {answer!r}")
ws.close()
ok = bool(answer) and "omni" in answer.lower()
print("RESULT:", "LIVE-SENTINEL-MATCH" if ok else ("LIVE-TEXT" if answer else "EMPTY"))
