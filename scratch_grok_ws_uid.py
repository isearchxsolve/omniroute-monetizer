"""scratch_grok_ws_uid.py — test whether the ws URL `uid` param is the session key.

Chrome connected with uid=4e1bbc17-d505-4ff2-ab66-e9c5b7409043. If the server keys the realtime
session by uid (device id), connecting with Chrome's EXACT uid should make us the same device —
possibly taking over the session even while Chrome's tab is open.
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
captured_url = d["recorded_ws"]["url"]
captured_uid = captured_url.split("uid=")[1]
print("captured uid:", captured_uid)

def try_connect(uid, label, conv=None):
    ws_url = f"wss://grok.com/ws/mgw/?uid={uid}"
    try:
        ws = wsc.create_connection(ws_url, timeout=20, suppress_origin=True,
                                   max_size=64*1024*1024,
                                   header=["Cookie: " + cookie, "Origin: https://grok.com",
                                           "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                      "Chrome/151.0.0.0 Safari/537.36"])
    except Exception as e:
        print(f"[{label}] connect failed: {type(e).__name__}: {e}")
        return None
    conv = conv or str(uuid.uuid4())
    ws.send(json.dumps({"session_id": conv, "event": {"type": "session.create",
        "event_id": f"evt_init_{uuid.uuid4()}",
        "session": {"model": model, "x_grok": {"protocol_capabilities": caps,
                    "conversation_id": conv, "load_existing": False, "use_chunk": True,
                    "enable_side_by_side": True, "force_side_by_side": False,
                    "enable_image_generation": True, "image_generation_count": 2,
                    "disable_text_follow_ups": False, "disable_artifact": True,
                    "force_concise": False}}}}))
    end = time.monotonic() + 12
    result = None
    while time.monotonic() < end:
        ws.settimeout(4)
        try:
            m = json.loads(ws.recv())
        except Exception as e:
            print(f"[{label}] recv err: {type(e).__name__}"); break
        typ = (m.get("event") or {}).get("type")
        print(f"[{label}] event: {typ}")
        if typ in ("session.created", "session.moved", "error"):
            result = typ
            break
    ws.close()
    return result

r1 = try_connect(captured_uid, "captured-uid")
print("captured-uid result:", r1)
