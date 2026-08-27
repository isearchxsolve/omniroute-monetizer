"""scratch_grok_ws_dump.py — capture the FULL raw frames of a live exchange to find the text field."""
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
    if "__error__" in m: break
    if (m.get("event") or {}).get("type") == "session.created": created = True; break
print("OWNER:", created)
if not created: ws.close(); sys.exit(1)

send({"session_id": conv, "event": {"type": "response.create",
      "event_id": f"evt_resp_{int(time.time()*1000)}",
      "item": {"type": "message", "role": "user",
               "x_grok": {"client_message_id": str(uuid.uuid4()),
                          "input_chunks": [{"text": {"text": "Reply exactly one word: Omni."}}]}},
      "parent_response_id": None}})

frames = []
done = False
end = time.monotonic() + 90
while time.monotonic() < end and not done:
    m = recv(10)
    if "__error__" in m: break
    ev = m.get("event") or {}
    typ = ev.get("type")
    frames.append(m)
    if typ == "response.done": done = True
    elif typ == "error": break

# dump the interesting frames fully
print(f"\n=== {len(frames)} frames ===")
for m in frames:
    ev = m.get("event") or {}
    typ = ev.get("type")
    if typ in ("response.chunk", "response.output_text.done", "response.output_item.done",
               "response.content_part.added", "response.content_part.done", "conversation.item.added"):
        print(f"\n--- {typ} ---")
        print(json.dumps(ev)[:900])
ws.close()
