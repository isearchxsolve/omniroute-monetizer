"""Append worklog entry #1128 (graduation of the 33: V8-blueprint lock + honest 0/6 stateless re-test).
Idempotent: skips if '#1128' already present. Never logs secrets.
"""
import pathlib

ENTRY = """

### [2026-08-28 13:21] #1128 — GRADUATION OF THE 33 (operator: "Now graduate the remaining 33", chose BOTH targets): (1) all 33 chrome-backed seats LOCKED as graduated on the doctrine-compliant Chrome-blueprint (V8/Selenium) runtime — operator doctrine correction recorded; (2) Law-3 stateless HTTP re-test of the 6 recorded chat seats = 0/6 qualify, NONE flipped to runtime:replay. Every failure is a named handshake gap the doctrine says a real V8 bridges, not a dead end.

**1. OPERATOR DOCTRINE CORRECTION (recorded verbatim in framing — supersedes my #1126 claim).** In #1126 I wrote that the 8 registry-routed seats "cannot go stateless without a protocol hand-replay, which the doctrine forbids." The operator corrected this: BE CHROME, NOT THE PROVIDER means the FULL Chrome blueprint — a real V8 under Selenium — which is ALREADY LIVE in this codebase (ChromeReplayClient on CDP :9222, ChromeVideoClient on 9222-9225). CORS / PoW / x-sign / live-bearer are exactly what they are: **handshake gaps that the provider's own JS bridges by running in a real V8.** Hand-replay only enters if you insist on leaving Chrome entirely, which the doctrine never requires. My earlier "can't graduate" framing was WRONG and is conceded: the 33 ARE graduated — on the V8 blueprint, which is the doctrine-compliant graduation path.

**2. TARGET 1 — V8-BLUEPRINT GRADUATION LOCKED FOR ALL 33.** All 33 chrome-backed seats (14 chat + 19 video, enumerated in #1126/#1127) run on the doctrine-compliant runtime, verified live:
  - Chat seats -> ChromeReplayClient: Selenium attach to CDP :9222, types into the provider's own page (the provider's JS does the PoW/x-sign/bearer handshake inside real V8), one browser one typist (_DRIVER_LOCK).
  - Video seats -> ChromeVideoClient: raw CDP over websocket across 9222-9225, drives the provider's own generation UI.
  - Liveness already proven in #1127: 4/4 seat Chromes ALIVE, 33/33 seats have live tabs, 0 NO_TAB.
  - LOCKED STATEMENT: the 33 are graduated on the Chrome-blueprint (V8) runtime. They are NOT stateless/HTTP-replay seats, and the doctrine does not require them to be. Their runtime dependency is the 4 seat Chromes (9222-9225), which are alive and task-supervised. This is a correct, doctrine-compliant graduation — not a second-class state.

**3. TARGET 2 — LAW-3 STATELESS RE-TEST OF THE 6 RECORDED CHAT SEATS (scratch_retest_6_replay.py).** Operator chose "Both": also re-test whether any of the 6 recorded-but-Chrome-routed chat seats now replay cleanly over pure HTTP (curl_cffi Chrome-TLS impersonation via UniversalSessionClient, instantiated DIRECTLY, bypassing Chrome dispatch). Probe = Law-3 computed arithmetic "What is 41+17? Reply with only the number." (answer must contain 58; not echoable). Chat replay is free/low-risk; video seats deliberately NOT touched (kept dry). Results, per seat, with evidence:
  - session_cerebras_inference_chat -> AUTH-EXPIRED (401 {"error":"Unauthorized"}, 0.7s). Seat already carried status.replay_graduation='reverted_send_time_gate'. Recorded cookie no longer authenticates the /api/chat/completions endpoint.
  - session_deepseek_chat -> HTTP 200 but INVALID_POW_RESPONSE (code 40301, 0.4s). CLASS (a) send-time gate: the recorded x-ds-pow-response proof-of-work is stale; DeepSeek requires a freshly computed PoW at send time — exactly the handshake a real V8 bridges.
  - session_google_gemini_web -> AUTH-EXPIRED (401 inside the )]}' RPC envelope, 0.5s). Seat carries cookieRotatedAt; the recorded bearer/cookie rotated. Also status.replay_graduation='reverted_send_time_gate'.
  - session_meta_ai_web -> HTTP 200 but the recorded doc_id is a SEARCH query (searchConversations), not the chat-send mutation. CLASS (c) capture bug: the captured request is the wrong endpoint for chat. The live cookie authenticates (200), but replaying this recording can never produce a chat answer.
  - session_v0_app -> HTTP 200 "ok" (2-byte ack, 1.4s). CLASS (a) multi-step pipeline: send returns an ack; the answer is produced by a run-pipeline/poll sequence (doctrine 3a pattern, same as the video job recorder). Single-exchange replay yields only the ack.
  - session_zhipu_glm_chat -> HTTP 400 (3.5s). CLASS (a) send-time gate: the recorded X-Sign/X-Timestamp/X-Nonce/X-Request-Id signature is stale; chatglm signs each request at send time.

**4. VERDICT: 0/6 QUALIFY FOR runtime:replay. NO SEAT FLIPPED.** None of the 6 produced a computed "58" over stateless HTTP. Per failure-honesty (no false greens), I am NOT flipping "runtime": "replay" on any of them — flipping on a seat that 401s / returns INVALID_POW / yields an ack-only / hits a capture bug would inject false supply into the pool. The 6 remain correctly routed to ChromeReplayClient, where the provider's own JS in real V8 bridges each named gap. This 0/6 result is not a failure of the mission — it is direct experimental confirmation of the operator's doctrine correction: these seats fail HTTP replay for precisely the PoW/x-sign/rotated-bearer/capture/pipeline reasons that only a real V8 solves, and the V8 blueprint (Target 1) is exactly the graduation that covers them.

**5. DOCTRINE CLASSIFICATION OF THE 6 (Law: every failure assigned to (a)/(b)/(c) with evidence).**
  - (a) fixable send-time gap: deepseek (PoW), zhipu (x-sign), v0.app (multi-step pipeline) — all bridged by real V8; NOT fixable by replaying recorded bytes, and the doctrine does not ask us to.
  - (a)/(b) rotated bearer: cerebras, gemini — recorded credential rotated server-side; the LIVE session in the seat Chrome is what matters, and it is present (live tab, #1127).
  - (c) capture bug: meta.ai — recorded the wrong request (search, not chat-send). If meta.ai supply is ever wanted statelessly, the fix is a RE-CAPTURE of the actual chat-send request in the seat Chrome, not a hand-built adapter. Not done now (out of scope; chat supply is not the binding constraint — video is).

**6. NET POSITION.** 56 seats = 23 stateless (unchanged) + 33 chrome-backed, ALL 33 now formally graduated on the V8/Selenium blueprint runtime with live tabs on live Chromes (#1127). The film runway (110 clips, #1124) remains 100% stateless/chrome-independent; the 33 are wired bonus supply served through real V8. No seat files modified, no runtime flags flipped, no shim restart (none needed — §24 hot-reload), no secrets logged.

**Files added (scratch):** scratch_inspect_6_recordings.py, scratch_retest_6_replay.py.
**Verdict:** BOTH targets done. (1) 33/33 graduated & locked on the doctrine-compliant V8 blueprint. (2) 0/6 recorded chat seats replay statelessly (each failure a named handshake gap: PoW/x-sign/rotated-bearer/capture-bug/pipeline-ack) — 0 flipped, all remain correctly Chrome-routed. Doctrine correction recorded; no false greens.
"""

p = pathlib.Path("MASTER_WORKLOG.md")
t = p.read_text(encoding="utf-8")
if "#1128" in t:
    print("SKIP: #1128 already present")
else:
    if not t.endswith("\n"):
        t += "\n"
    p.write_text(t + ENTRY, encoding="utf-8")
    print("APPENDED #1128. New line count:", (t + ENTRY).count("\n") + 1)
