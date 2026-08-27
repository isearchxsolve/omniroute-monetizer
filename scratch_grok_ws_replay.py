"""scratch_grok_ws_replay.py — PROOF OF CONCEPT: replay grok over a raw websocket from Python.

Doctrine 3a: Chrome speaks this websocket, so we speak it too. This opens the SAME ws URL
with the SAME cookie the capture recorded, sends session.create + response.create, and reads
the streamed answer. No Chrome in the request path.

The one stateful field is the conversation's current leaf (parent_response_id). It advances
with every message, so we read the live history on connect and append to the TRUE leaf rather
than replaying a stale id.
"""
import sys, json, time, uuid, pathlib
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import websocket  # websocket-client

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
ws_info = d["recorded_ws"]
cookie = d["cookie_header"]

# The captured session.create frame tells us the conversation + model.
sent_frames = ws_info["frames_sent"]
create_frame = json.loads(sent_frames[0])
resp_frame = json.loads(sent_frames[ws_info["sentinel_frame_index"]])

conversation_id = create_frame["session_id"]
model = create_frame["event"]["session"]["model"]
x_grok_create = create_frame["event"]["session"]["x_grok"]
print(f"conversation_id={conversation_id}  model={model}")

# Fresh uid per connection (Chrome generates one per socket).
ws_url = f"wss://grok.com/ws/mgw/?uid={uuid.uuid4()}"
print(f"connecting {ws_url}")

PROMPT = "Reply exactly one word: Omni."

ws = websocket.create_connection(
    ws_url, timeout=30, suppress_origin=True, max_size=64 * 1024 * 1024,
    header=["Cookie: " + cookie, "Origin: https://grok.com",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"])
print("connected")

def send(obj):
    ws.send(json.dumps(obj))

def recv(timeout=30):
    ws.settimeout(timeout)
    try:
        return json.loads(ws.recv())
    except Exception as e:
        return {"__error__": f"{type(e).__name__}: {e}"}

# ---- 1. session.create (reuse captured shape; load_existing to get history) -----------------
send({
    "session_id": conversation_id,
    "event": {
        "type": "session.create",
        "event_id": f"evt_init_{uuid.uuid4()}",
        "session": {
            "model": model,
            "x_grok": {
                "protocol_capabilities": x_grok_create.get("protocol_capabilities", []),
                "conversation_id": conversation_id,
                "load_existing": True,
                "use_chunk": True,
                "enable_side_by_side": True,
                "force_side_by_side": False,
                "enable_image_generation": True,
                "image_generation_count": 2,
                "disable_text_follow_ups": False,
                "disable_artifact": True,
                "force_concise": False,
            },
        },
    },
})

# ---- 2. read until we know the current leaf -------------------------------------------------
leaf = None
history_ids = []
deadline = time.monotonic() + 20
got_created = False
while time.monotonic() < deadline:
    msg = recv(5)
    if "__error__" in msg:
        print("recv error:", msg["__error__"]); break
    ev = (msg.get("event") or {})
    typ = ev.get("type")
    if typ == "session.created":
        got_created = True
        print("session.created OK")
    elif typ == "conversation.attached":
        print("conversation.attached mode=", ev.get("mode"))
    elif typ == "conversation.history.item":
        item = ev.get("item") or {}
        iid = item.get("id")
        role = item.get("role")
        history_ids.append(iid)
        leaf = iid  # last item seen is the current leaf
    elif typ in ("error",):
        print("ERROR EVENT:", json.dumps(ev)[:400]); break
    else:
        # any other event after history is done means history stream ended
        if got_created and history_ids and typ not in ("conversation.history.item",):
            print(f"(history done, next event: {typ})")
            break
print(f"history items={len(history_ids)}  current leaf={leaf}")

if not leaf:
    print("NO LEAF FOUND — aborting")
    sys.exit(1)

# ---- 3. response.create with the prompt, parent = true leaf ---------------------------------
send({
    "session_id": conversation_id,
    "event": {
        "type": "response.create",
        "event_id": f"evt_resp_{int(time.time()*1000)}",
        "item": {
            "type": "message",
            "role": "user",
            "x_grok": {
                "client_message_id": str(uuid.uuid4()),
                "input_chunks": [{"text": {"text": PROMPT}}],
            },
        },
        "parent_response_id": leaf,
    },
})
print("response.create sent, waiting for answer...")

# ---- 4. read until response.done; collect the assistant answer ------------------------------
answer_parts = []
done = False
deadline = time.monotonic() + 90
last_event = None
while time.monotonic() < deadline and not done:
    msg = recv(10)
    if "__error__" in msg:
        print("recv error:", msg["__error__"]); break
    ev = (msg.get("event") or {})
    typ = ev.get("type")
    last_event = typ
    if typ == "response.output_text.delta":
        delta = (ev.get("delta") or "")
        answer_parts.append(delta)
    elif typ in ("response.output_item.done", "conversation.history.item"):
        # final assistant message carries output_chunks with the full text
        item = ev.get("item") or {}
        if item.get("role") == "assistant":
            for ch in (item.get("x_grok") or {}).get("output_chunks", []):
                tx = (ch.get("text") or {})
                if tx.get("channel") == "CHANNEL_ASSISTANT_RESPONSE" and tx.get("text"):
                    answer_parts = [tx["text"]]  # authoritative full text
    elif typ == "response.done":
        done = True
        print("response.done status=", (ev.get("response") or {}).get("status"))
    elif typ == "error":
        print("ERROR EVENT:", json.dumps(ev)[:400]); break

answer = "".join(answer_parts).strip()
print(f"\nlast_event={last_event}")
print(f"ANSWER ({len(answer)} chars): {answer!r}")
ws.close()
print("\nRESULT:", "LIVE" if answer else "EMPTY")
