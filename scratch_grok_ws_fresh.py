"""scratch_grok_ws_fresh.py — grok ws replay with a FRESH conversation (no session.moved clash)."""
import sys, json, time, uuid, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import websocket

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
cookie = d["cookie_header"]
create_frame = json.loads(d["recorded_ws"]["frames_sent"][0])
model = create_frame["event"]["session"]["model"]
caps = create_frame["event"]["session"]["x_grok"].get("protocol_capabilities", [])

conversation_id = str(uuid.uuid4())   # FRESH conversation — no clash with Chrome's socket
ws_url = f"wss://grok.com/ws/mgw/?uid={uuid.uuid4()}"
print(f"fresh conversation_id={conversation_id}")

ws = websocket.create_connection(
    ws_url, timeout=30, suppress_origin=True, max_size=64 * 1024 * 1024,
    header=["Cookie: " + cookie, "Origin: https://grok.com",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"])

def send(obj): ws.send(json.dumps(obj))
def recv(timeout=15):
    ws.settimeout(timeout)
    try:
        return json.loads(ws.recv())
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}

send({"session_id": conversation_id,
      "event": {"type": "session.create", "event_id": f"evt_init_{uuid.uuid4()}",
                "session": {"model": model,
                            "x_grok": {"protocol_capabilities": caps,
                                       "conversation_id": conversation_id,
                                       "load_existing": False, "use_chunk": True,
                                       "enable_side_by_side": True, "force_side_by_side": False,
                                       "enable_image_generation": True, "image_generation_count": 2,
                                       "disable_text_follow_ups": False, "disable_artifact": True,
                                       "force_concise": False}}}})

created = False
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    msg = recv(5)
    if "__error__" in msg:
        print("recv error:", msg["__error__"]); break
    ev = msg.get("event") or {}
    typ = ev.get("type")
    print("event:", typ)
    if typ == "session.created":
        created = True
        break
    if typ == "session.moved":
        print("session.moved even on fresh conversation — unexpected")
        break
    if typ == "error":
        print("ERROR:", json.dumps(ev)[:400]); break

if not created:
    print("NO session.created — abort"); sys.exit(1)

PROMPT = "Reply exactly one word: Omni."
send({"session_id": conversation_id,
      "event": {"type": "response.create", "event_id": f"evt_resp_{int(time.time()*1000)}",
                "item": {"type": "message", "role": "user",
                         "x_grok": {"client_message_id": str(uuid.uuid4()),
                                    "input_chunks": [{"text": {"text": PROMPT}}]}},
                "parent_response_id": None}})
print("response.create sent (parent=None, fresh conversation)")

answer_parts = []
done = False
deadline = time.monotonic() + 90
events_seen = []
while time.monotonic() < deadline and not done:
    msg = recv(10)
    if "__error__" in msg:
        print("recv error:", msg["__error__"]); break
    ev = msg.get("event") or {}
    typ = ev.get("type")
    events_seen.append(typ)
    if typ == "response.output_text.delta":
        answer_parts.append(ev.get("delta") or "")
    elif typ in ("response.output_item.done", "conversation.history.item"):
        item = ev.get("item") or {}
        if item.get("role") == "assistant":
            for ch in (item.get("x_grok") or {}).get("output_chunks", []):
                tx = ch.get("text") or {}
                if tx.get("channel") == "CHANNEL_ASSISTANT_RESPONSE" and tx.get("text"):
                    answer_parts = [tx["text"]]
    elif typ == "response.done":
        done = True
    elif typ == "error":
        print("ERROR:", json.dumps(ev)[:400]); break

answer = "".join(answer_parts).strip()
print("\nevents seen:", events_seen[:40])
print(f"ANSWER ({len(answer)} chars): {answer!r}")
ws.close()
print("RESULT:", "LIVE" if answer else "EMPTY")
