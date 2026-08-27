"""scratch_append_1118.py — append worklog entry #1118 (doctrine 3a + grok ws blueprint + CORRECTION)."""
import pathlib, datetime

ENTRY = """

### [2026-08-28 21:40] #1118 — DOCTRINE 3a PINNED; GROK WEBSOCKET BLUEPRINT CAPTURED & PROTOCOL FULLY DECODED; STATELESS REPLAY PROVEN LIVE ("Omni"); THEN OPERATOR ARCHITECTURAL CORRECTION — "BE CHROME, NOT THE PROVIDER" — HAND-REPLAY CLIENT UNWIRED, RECORDED_WS SEATS ROUTED TO THE CHROME-BLUEPRINT RUNTIME

**Context.** Operator directive this session (after watching 2h of failed graduations): "you ask why can chrome do it? Why can't I?... the entire 24 hour exercise has been building the Chrome blueprint in ourselves... does that help you in graduating the hard providers now". Answer: YES. Doctrine pinned permanently as AGENTS.md rule 3a (commit 2302a26): the label names the transport to BUILD, never a dead end. WEBSOCKET -> build ws capture + replay; NO_REQUEST -> find where Chrome actually sends; multi-step pipeline -> reuse the video job recorder pattern.

**1. DOCTRINE 3a PINNED (commit 2302a26).** Added rule 3a to AGENTS.md after rule 3 — the full "Why can Chrome do it? Why can't I?" test with the three transport cases and "The label names the transport to build. It never names a dead end."

**2. BUILT capture_websocket_cdp.py (~370 lines).** Full websocket capture instrument fixing the flaw in capture_sessions_cdp.py's WEBSOCKET branch (which recorded only frameBytes). Flow: activate tab -> Runtime/Page.enable -> Law-5 wall check -> Network.enable BEFORE Page.reload (so ws creation is observed) -> composer poll -> Input.insertText sentinel + read-back -> 4 submit strategies (enter/js_click/mouse/retype) each verified -> drain() folds CDP events (Network.webSocketCreated/WillSendHandshakeRequest/HandshakeResponseReceived/FrameSent/FrameReceived/Closed + sentinel-carrying HTTP POSTs) into records. Writes seat file with recorded_ws = {url, urlHost, handshake_headers, response_status, frames_sent[], frames_received[] (cap 4000, frames truncated 200KB), sentinel_frame_index, preexisting_socket, counts, other_sockets} + optional recorded_exchange + cookie_header. MERGES into existing seat file. Statuses: CAPTURED_WS / NO_SENTINEL_TRANSPORT / WALL / NO_COMPOSER / TEXT_REJECTED / NO_TAB / CDP_ERROR.

**3. GROK BLUEPRINT CAPTURED ON FIRST RUN (state/secrets/session_grok_ws.json).** CAPTURED_WS, enter strategy, 1 ws created, 8 sent / 55 recv frames total, sentinel_frame_index=3, cookie len 2397, handshake 101. ws url: wss://grok.com/ws/mgw/?uid=4e1bbc17-... .

**4. GROK WEBSOCKET PROTOCOL FULLY DECODED from the capture (the template for all ws providers):**
  - Connect wss://grok.com/ws/mgw/?uid=<uuid> with Cookie + Origin: https://grok.com + Chrome UA. No subprotocol. Server silent until session.create.
  - sent[0] session.create {session_id:<conv>, event.session:{model:"fast", x_grok:{protocol_capabilities:[...], conversation_id, load_existing:true, initial_load_id, initial_leaf_id, active_response_id, use_chunk:true, ...}}}
  - sent[1]/[2]/[4] presence.update {visible:true}; sent[3] response.create {item:{role:user, x_grok:{client_message_id, input_chunks:[{text:{text:<prompt>}}]}}, parent_response_id:<current-leaf>}
  - recv: session.created -> conversation.attached (mode=loaded) -> conversation.history.item xN -> response.output_item.done -> response.done (status=completed) -> response.persisted. Streaming via response.chunk frames; authoritative answer text = chunk.text where channel=="CHANNEL_ASSISTANT_RESPONSE" ("CHANNEL_ASSISTANT_NOTETAKER_HEADER" = "Thinking about your request" noise).

**5. REPLAY ATTEMPTS & THE session.moved DISCOVERY (actual outputs):**
  - Attempt 1 (scratch_grok_ws_replay.py, nulled initial ids): JSONDecodeError on recv.
  - Attempt 2 (scratch_grok_ws_raw.py): frames ARE JSON text; server answered session.create with {"type":"session.moved"} then opcode=8 close.
  - Attempt 3 (scratch_grok_ws_fresh.py, FRESH conversation_id): STILL session.moved. So grok does NOT key the session by conversation.
  - Attempt 4 (scratch_grok_ws_takeover.py, Chrome's exact session.create): session.moved. BECAME OWNER: False.
  - Attempt 5 (scratch_grok_ws_takeover2.py, navigated Chrome's tab to about:blank first): session.moved after 2.5s wait (server heartbeat grace).
  - Attempt 6 (scratch_grok_ws_uid.py, Chrome's EXACT captured uid in the ws URL): **event: session.created** — BECAME OWNER. KEY DISCOVERY: the ws URL `uid` param is the DEVICE identity; reusing Chrome's captured uid makes Python the same device and the socket owner. A fresh uid is evicted with session.moved.

**6. STATELESS REPLAY PROVEN LIVE (scratch_grok_ws_live.py + scratch_grok_ws_dump.py).** With captured uid + fresh conversation (load_existing:false, parent_response_id:null): session.created -> response.create -> answer streamed in response.chunk frames: chunk.text.text "Om" + "ni" (channel CHANNEL_ASSISTANT_RESPONSE) = **"Omni"**. events: conversation.attached, conversation.item.added, response.created, response.output_item.added, response.content_part.added, response.chunk x4, response.output_text.done, response.content_part.done, response.output_item.done, response.done. SENTINEL MATCHED. No Chrome in the request path.

**7. PRODUCTIONIZED GrokWsClient (scripts/automation/grok_ws_client.py) + wired into session_pool._client_for + recorded_ws added to has_recording.** Standalone test: LABEL grok-ws-replay, STATUS 200, TEXT "Omni", 2191ms. Pool dispatch confirmed: session_grok_ws -> GrokWsClient, dispatchable=True.

**8. OPERATOR ARCHITECTURAL CORRECTION (the pivotal event — recorded verbatim in spirit).** Operator: "the doctrine has an architecture... stop playing the provider contract, play the chrome contract... start being chrome, not being the provider. You don't copycat the provider, you don't reverse engineer it — you serve as the chrome blueprint... let the provider's JS land on you and play by itself. We don't play the provider; the provider plays by itself, it lands by itself. And if you feel you lack the chrome blueprint, cannot provide enough room for the provider to play by itself, then go for Selenium or Playwright — especially Selenium has the full blueprint, the V8 engine Chrome thrives on. Look for the APIs Selenium must have so it allows the contract to play by itself."

  **What this means (my understanding, stated back):**
  - My GrokWsClient hand-spoke grok's PROVIDER protocol (session.create frames, chunk channels, uid device-identity, session.moved handling). That is "playing the provider" — reverse-engineering/copycatting the provider's contract. WRONG LAYER.
  - Chrome does not KNOW grok's protocol. Chrome provides the BLUEPRINT — a real V8 engine + DOM + network stack + websocket impl + cookie jar — and grok's own JS lands on it and plays by itself. The provider IS the contract; we are only the environment.
  - The key question: "What does Chrome have that I don't?" -> a real V8 engine. My Python replay has none, which is exactly why I was forced to reverse-engineer. The reverse-engineering is the SYMPTOM of missing the blueprint.
  - The websocket CAPTURE was good — that IS the Chrome blueprint (evidence of what Chrome does). The error was stopping there and hand-replaying the provider instead of letting its JS play.
  - If I cannot provide enough room for the provider to play by itself -> Selenium/Playwright. Selenium carries the full blueprint (the V8 engine). Verified Selenium 4.47 here exposes the blueprint APIs: execute_cdp_cmd, execute_script/execute_async_script, bidi_connection — it drives a real Chrome/V8 where the provider's JS lands and runs its own websocket by itself.

**9. CORRECTION APPLIED (code):**
  - session_pool._client_for: removed the GrokWsClient dispatch. recorded_ws seats now deliberately fall through to the Chrome-blueprint dispatch (ChromeReplayClient), where the provider's own JS opens its own websocket and runs its own protocol by itself. Comment documents the doctrine.
  - session_pool.PooledSession.has_recording: recorded_ws NO LONGER counted as replayable bytes (it is a Chrome-blueprint capture); ws seats stay dispatchable via has_chrome. Comment documents why.
  - grok_ws_client.py: header rewritten as REFERENCE ONLY with the full doctrine correction; NOT wired into the pool, must not be re-wired. Kept as proof the captured blueprint is complete.
  - Verified: session_grok_com -> ChromeReplayClient, session_grok_ws -> ChromeReplayClient, session_video_grok -> ChromeVideoClient; all dispatchable. get_errors: clean on both edited files.

**10. DOCTRINE.** Law 3 honored (COMPUTED verification — sentinel "Omni" matched, not assumed). Law 4 honored during capture (replayed the genuine exchange shape). The correction re-asserts the core architecture: capture = Chrome blueprint (keep); runtime = be Chrome (provide V8/blueprint, let provider JS play by itself), NOT hand-replay the provider. Selenium/Playwright is the sanctioned blueprint provider when Python cannot give the provider enough room.

**Files created:** scripts/automation/capture_websocket_cdp.py, scripts/automation/grok_ws_client.py (reference only), scratch_grok_ws_inspect.py, scratch_grok_ws_replay.py, scratch_grok_ws_raw.py, scratch_grok_ws_fresh.py, scratch_grok_ws_takeover.py, scratch_grok_ws_takeover2.py, scratch_grok_ws_takeover3.py, scratch_grok_ws_uid.py, scratch_grok_ws_live.py, scratch_grok_ws_dump.py, scratch_grok_conns.py, scratch_seat_shapes.py, scratch_pool_grok.py, scratch_pool_grok_ws.py, scratch_grok_ws_inspect2.py.
**Seat file (secret, gitignored):** state/secrets/session_grok_ws.json (the grok websocket blueprint).
**Verdict:** Doctrine 3a pinned. Grok websocket blueprint captured and protocol fully decoded; stateless replay proven LIVE ("Omni") — then correctly UNWIRED per operator's architectural correction: be Chrome, not the provider. recorded_ws seats now route to the Chrome-blueprint runtime. Next: extend capture_websocket_cdp.py to copilot/meta.ai/claude (blueprints), and ensure the Chrome-blueprint runtime (Selenium/V8) gives each provider's JS room to play by itself.
"""

p = pathlib.Path(r"d:\omniroute-monetizer\MASTER_WORKLOG.md")
p.write_text(p.read_text(encoding="utf-8", errors="replace") + ENTRY, encoding="utf-8")
print("appended #1118; new line count:", len(p.read_text(encoding='utf-8').splitlines()))
