"""Append worklog entry #1132 (meta.ai websocket transport discovery) idempotently."""
import pathlib

f = pathlib.Path("MASTER_WORKLOG.md")
text = f.read_text(encoding="utf-8")
if "#1132" in text:
    print("SKIP: #1132 already present")
    raise SystemExit(0)

entry = """

### [2026-08-28 15:05] #1132 — P2 INVESTIGATION: meta.ai chat-send is a WEBSOCKET, not HTTP. Decoded the full frame: 8-byte binary header + JSON{req-id, payload:base64(protobuf)}. The 64-hex hash is STATIC across sends (device fingerprint, NOT a per-message signature) — replay is tractable. Auth = 5 cookies (datr/dpr/ecto_1_sess/sidebar_state/wd). Endpoint wss://gateway.meta.ai/ws. This is the WEBSOCKET transport class override #1130 anticipated; a ws replay client is the build target.

**1. THE DISCOVERY (why the re-capture failed).** Re-ran capture_sessions_cdp.py for "Meta AI Web" on seat Chrome :9222 (the established capture flow, seat's own dedicated tab). Result: NO_REQUEST — text landed, all 4 submit strategies fired, 10 HTTP POSTs + 48 ws frames seen, but NO POST carried the sentinel. Doctrine 3a's NO_REQUEST rule says: find where Chrome actually sends. Diagnostic (scratch_meta_where_send.py) confirmed: the 5 HTTP POSTs to /api/graphql are all housekeeping (conversation metadata, lastSeenMessageId, doc_id queries) — none carry the prompt. **The actual chat-send goes out over a websocket as a base64-encoded protobuf frame, and the response ("Omni") streams back over the same socket.** This is exactly the WEBSOCKET transport class the operator override #1130 named: "build a websocket capture + websocket replay client."

**2. FRAME STRUCTURE (fully decoded, scratch_meta_ws_decode.py + scratch_meta_pb_decode.py).**
  - Outer envelope: 8-byte binary header `0d00007805000380` + JSON `{"req-id": "<uuid>", "payload": "<base64 protobuf>"}`. No trailer bytes.
  - Inner protobuf (1000 bytes), field map:
    - field 1 (831B): the message body — `KADABRA__CHAT__UNIFIED_INPUT_BAR` marker, conversation UUID, device info ("Abra Web Main Keyb", "desktop_web", Windows UA), locale en-GB, timezone Asia/Calcutta, feature-flag list (stocks/weather/carousels/media_gallery), the prompt, and a **64-hex SHA-256 hash** `@3e64e7b0c282fb56772482159cf03171691ad1b3480d6993a842b040221e38c1`.
    - field 2 (163B): per-message — a fresh message UUID, conversation UUID, epoch-ms timestamp, a snowflake varint, an `e.00...` session token, and the prompt text again.
  - **HASH STABILITY TEST (the decisive feasibility check, scratch_meta_ws_hash.py):** sent the sentinel TWICE, extracted the hash from both captured frames — IDENTICAL (`3e64e7b0...`), while req-id and message UUID differed. Conclusion: the hash is a STATIC device/session fingerprint, NOT a per-message signature. No signing algorithm needs reverse-engineering. This is the single fact that makes replay tractable.

**3. AUTH + ENDPOINT.**
  - Endpoint: `wss://gateway.meta.ai/ws` (found by grepping the 166 loaded scripts; also `wss://shortwave.meta.ai/v2/transcription` for voice, irrelevant).
  - Auth cookies for www.meta.ai + gateway.meta.ai (names only, values never logged): `datr`, `dpr`, `ecto_1_sess`, `sidebar_state`, `wd`. Auth-ish: datr, wd. The ws handshake rides these cookies.
  - NOTE: the ws connects LAZILY (after hydration/interaction), not on page load — a reload with Network.enable produced 480 events but 0 ws events; the frame captures worked because the socket was already live from prior interaction. A ws replay client must therefore open the socket itself with the cookies, not rely on a page load.

**4. REPLAY FEASIBILITY VERDICT.** TRACTABLE. Every per-message field is client-generated (fresh UUIDs, epoch-ms timestamp, snowflake) — none is server-issued at send time. The only opaque value (the 64-hex hash) is static and can be lifted verbatim from a capture. So a pure-Python ws client can: open wss://gateway.meta.ai/ws with the 5 cookies, send the reconstructed frame (new req-id + message UUID + timestamp, static hash, injected prompt), and read the streamed response. Remaining unknowns to resolve in the BUILD step: (a) exact ws subprotocol/first-handshake frames (the socket may expect an init/hello frame before chat frames — need to capture the socket-open sequence, not just a chat frame); (b) whether the `e.00...` token in field 2 rotates per session or is static; (c) response-frame parsing to extract the assistant text for Law-3 verification.

**5. LAW-3 / DOCTRINE STATUS.** No graduation yet — this is investigation, not a flip. The seat stays Chrome-backed (session_meta_ai_web unchanged on disk; the failed re-capture did NOT overwrite it, since save() only fires on a sentinel-carrying POST). When the ws client is built, graduation gates on a Law-3 computed probe (arithmetic "41+17"->"58" over the ws, never echoable). Law 5 walls still FULL STOP. Override #1130 authorizes this hand-roll.

**6. NEXT (P2 build).** Capture the socket-OPEN sequence (Network.enable around a fresh ws connect — may need to force a reconnect by killing the socket or waiting for idle timeout), record init frames, then build meta_ws_replay.py (websocket-client transport, cookie auth, frame reconstruction, response parse), Law-3 verify, then flip runtime. If the socket-open sequence proves un-capturable without a page load, fall back to driving one page load in the seat Chrome to harvest the open handshake, then serve stateless thereafter.

**Files added (scratch):** scratch_meta_recon.py, scratch_meta_recon2.py, scratch_meta_recon3.py, scratch_meta_where_send.py, scratch_meta_ws_decode.py, scratch_meta_ws_hash.py, scratch_meta_ws_url.py, scratch_meta_ws_handshake.py, scratch_meta_ws_hook.py, scratch_meta_ws_dump.py, scratch_meta_pb_decode.py.
**Artifacts (state, gitignored):** state/meta_ws_frames.json (captured sent+recv frames), state/meta_ws_payload.bin (decoded protobuf), state/meta_ws_handshake.json, state/capture_report_9222.json.
**Verdict:** meta.ai is a WEBSOCKET seat, not HTTP. Replay is tractable (static hash, client-generated per-message fields, cookie auth). Build target = a pure-Python ws replay client. No graduation yet; investigation logged, seat untouched.
"""

f.write_text(text.rstrip() + entry, encoding="utf-8")
print("APPENDED #1132; new line count:", len(f.read_text(encoding='utf-8').splitlines()))
