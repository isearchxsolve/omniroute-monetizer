"""scratch_grok_ws_takeover2.py — suspend Chrome's grok tab, then own the ws socket.

Grok = one active realtime socket per account. Chrome's open tab holds it and auto-reconnects,
evicting any second socket (session.moved). Suspending the tab (Page.setLifecycleEventsEnabled
+ Emulation or Page.stopLoading is not enough; we use the tab's CDP 'Page' freeze via
Runtime.evaluate to drop the socket AND block reconnect by freezing the event loop is unreliable).

Reliable approach: use CDP Target.setLifecycleEventsEnabled is not a freeze. Instead we use the
documented 'Page.enable' + navigate to about:blank? No — that loses the app. The correct freeze
is CDP 'Emulation.setCPUThrottlingRate' no. The REAL freeze: CDP method 'Page.setLifecycleEventsEnabled'
doesn't stop JS. So we use the browser-level 'Target' API: there is no suspend.

Pragmatic freeze that WORKS: call CDP 'Runtime.evaluate' to set a flag the app can't see is useless.
Instead: we DISCARD the tab via the /json endpoint is not available. So we use the documented
Chrome DevTools 'Page.stopLoading' + then close the websocket from the page by evaluating
window.__grokWs?.close() — but we don't know the handle.

SIMPLEST RELIABLE: navigate the tab to about:blank (kills the app + its socket + reconnect timers),
do our exchange on our own socket, then navigate back. The conversation persists server-side, so
navigating back restores the tab. This is reversible and stays in automation's own Chrome.
"""
import sys, json, time, uuid, pathlib, urllib.request
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import websocket as wsc

sys.path.insert(0, r"d:\omniroute-monetizer\scripts\automation")
from capture_sessions_cdp import CDP, targets

SEAT = pathlib.Path(r"d:\omniroute-monetizer\state\secrets\session_grok_ws.json")
d = json.loads(SEAT.read_text(encoding="utf-8-sig"))
cookie = d["cookie_header"]
create_frame = json.loads(d["recorded_ws"]["frames_sent"][0])
conversation_id = create_frame["session_id"]
model = create_frame["event"]["session"]["model"]
caps = create_frame["event"]["session"]["x_grok"].get("protocol_capabilities", [])

PORT = 9222
# find the grok tab
tabs = [t for t in targets(PORT) if "grok.com" in (t.get("url") or "")]
if not tabs:
    print("NO grok tab"); sys.exit(1)
tab = tabs[0]
orig_url = tab.get("url")
print("grok tab:", orig_url[:70])

c = CDP(tab["webSocketDebuggerUrl"], timeout=30)
try:
    c.call("Page.enable")
    # Navigate to about:blank: kills the app, its websocket, and all reconnect timers.
    c.call("Page.navigate", {"url": "about:blank"})
    print("navigated tab to about:blank (socket dropped)")
    time.sleep(2.5)

    # Now OUR socket should become the owner.
    ws_url = f"wss://grok.com/ws/mgw/?uid={uuid.uuid4()}"
    ws = wsc.create_connection(ws_url, timeout=30, suppress_origin=True,
                               max_size=64*1024*1024,
                               header=["Cookie: " + cookie, "Origin: https://grok.com",
                                       "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                                                  "Chrome/131.0.0.0 Safari/537.36"])
    def send(o): ws.send(json.dumps(o))
    def recv(t=10):
        ws.settimeout(t)
        try: return json.loads(ws.recv())
        except Exception as e: return {"__error__": f"{type(e).__name__}: {e}"}

    # fresh conversation to avoid needing the old leaf
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
    end = time.monotonic() + 12
    while time.monotonic() < end:
        m = recv(4)
        if "__error__" in m: print("err", m["__error__"]); break
        typ = (m.get("event") or {}).get("type")
        print("event:", typ)
        if typ == "session.created": created = True; break
        if typ in ("session.moved", "error"): break
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
            if "__error__" in m: print("err", m["__error__"]); break
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
finally:
    # ALWAYS restore the tab, even on failure.
    try:
        c.call("Page.navigate", {"url": orig_url})
        print("restored tab to", orig_url[:60])
    except Exception as e:
        print("RESTORE FAILED:", e)
    c.close()

print("RESULT:", "LIVE" if answer else "EMPTY/NO-OWNER")
