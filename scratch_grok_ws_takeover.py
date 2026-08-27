"""scratch_grok_ws_takeover.py — connect with Chrome's EXACT session_id + load_existing:true.

Tests whether a second socket can TAKE OVER the realtime session (become owner) or is always
evicted with session.moved. Answers: is grok one-active-socket-per-account, and who wins?
"""
import sys, json, time, uuid, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import websocket

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
cookie = d["cookie_header"]
create_frame = json.loads(d["recorded_ws"]["frames_sent"][0])
conversation_id = create_frame["session_id"]          # Chrome's exact session/conversation id
model = create_frame["event"]["session"]["model"]
xg = create_frame["event"]["session"]["x_grok"]

ws_url = f"wss://grok.com/ws/mgw/?uid={uuid.uuid4()}"
ws = websocket.create_connection(
    ws_url, timeout=30, suppress_origin=True, max_size=64 * 1024 * 1024,
    header=["Cookie: " + cookie, "Origin: https://grok.com",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"])

def recv(timeout=8):
    ws.settimeout(timeout)
    try:
        return json.loads(ws.recv())
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}

# Replicate Chrome's session.create EXACTLY (same session_id, load_existing true, same leaf ids).
ws.send(json.dumps(create_frame))
print("sent Chrome's exact session.create")

deadline = time.monotonic() + 12
events = []
while time.monotonic() < deadline:
    msg = recv(4)
    if "__error__" in msg:
        events.append("ERR:" + msg["__error__"]); break
    ev = msg.get("event") or {}
    typ = ev.get("type")
    events.append(typ)
    if typ in ("session.created", "session.moved", "error"):
        if typ == "error":
            print("ERROR:", json.dumps(ev)[:300])
        break
print("events:", events)
owner = "session.created" in events
print("BECAME OWNER:", owner)
ws.close()
