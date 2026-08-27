"""scratch_grok_ws_raw.py — what does grok's ws actually send back? Inspect raw frames."""
import sys, json, time, uuid, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import websocket

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
ws_info = d["recorded_ws"]
cookie = d["cookie_header"]
create_frame = json.loads(ws_info["frames_sent"][0])
conversation_id = create_frame["session_id"]
model = create_frame["event"]["session"]["model"]
x_grok_create = create_frame["event"]["session"]["x_grok"]

ws_url = f"wss://grok.com/ws/mgw/?uid={uuid.uuid4()}"
ws = websocket.create_connection(
    ws_url, timeout=30, suppress_origin=True, max_size=64 * 1024 * 1024,
    header=["Cookie: " + cookie, "Origin: https://grok.com",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"])
print("connected, subprotocol:", ws.subprotocol)

# First: read whatever arrives WITHOUT sending anything (hello/handshake frame?)
for i in range(3):
    ws.settimeout(8)
    try:
        opcode, data = ws.recv_data(control_frame=False)
    except Exception as e:
        print(f"frame {i}: recv error {type(e).__name__}: {e}")
        break
    print(f"\nframe {i}: opcode={opcode} len={len(data)}")
    if isinstance(data, bytes):
        print("  hex head:", data[:64].hex())
        try:
            print("  as utf8:", data[:300].decode("utf-8", "replace"))
        except Exception:
            pass
    else:
        print("  text:", str(data)[:300])

# Now send session.create and read the next frames raw
ws.send(json.dumps({
    "session_id": conversation_id,
    "event": {"type": "session.create", "event_id": f"evt_init_{uuid.uuid4()}",
              "session": {"model": model, "x_grok": dict(x_grok_create,
                          initial_load_id=None, initial_leaf_id=None, active_response_id=None,
                          load_existing=True)}}}))
print("\nsent session.create")
for i in range(6):
    ws.settimeout(10)
    try:
        opcode, data = ws.recv_data(control_frame=False)
    except Exception as e:
        print(f"post-create frame {i}: recv error {type(e).__name__}: {e}")
        break
    print(f"\npost-create frame {i}: opcode={opcode} len={len(data)}")
    if isinstance(data, bytes):
        print("  hex head:", data[:80].hex())
        print("  as utf8:", data[:400].decode("utf-8", "replace"))
    else:
        print("  text:", str(data)[:400])
ws.close()
