"""Append worklog entry #1129 (read-only enquiry: can the 33 reach the 23's stateless state?).
Idempotent: skips if '#1129' already present. Never logs secrets.
"""
import pathlib

ENTRY = """

### [2026-08-28 13:36] #1129 — READ-ONLY ENQUIRY (operator): "can the 33 graduated-on-V8 post-graduate to a similar state as the 23 stateless? V8 process is expensive, each execution will fork it." ANSWER: partially, tiered; and the expense model is NOT a per-execution fork — it is lock-serialization + resident-browser RAM. No changes made (pure enquiry).

**1. FACT-CHECK OF THE COST MODEL (correcting the fork assumption, verified in code).**
  - ChromeReplayClient does NOT fork/spawn V8 per execution. It ATTACHES to an already-running seat Chrome via Selenium `debuggerAddress 127.0.0.1:9222` (chrome_replay_client.py:108-121). The driver handle `_DRIVER` is a module-level singleton created once; the four seat Chromes (9222-9225) are long-lived resident processes started outside the pool. Zero process creation per request.
  - ChromeVideoClient likewise opens a raw CDP websocket to the SAME long-lived browsers (CDP_PORTS 9222-9225) — no spawn.
  - The REAL costs of the V8 path are: (a) SERIALIZATION — `_DRIVER_LOCK` is held for the WHOLE chat call (one browser, one typist), so chat calls queue single-file behind :9222; this is exactly why worklog #1113 calls runtime-Chrome an anti-pattern for scale; (b) UI latency — typing, waiting for the model to stream, ANSWER_TIMEOUT_S per call; (c) resident RAM of four Chromes (~50 tabs total, #1127). Video calls occupy their tab for the whole job duration but can spread across 4 browsers.
  - So "expensive" is true, but the expense is serialization + latency + RAM, not forking.

**2. FEASIBILITY CENSUS OF THE 33 (scratch_stateless_feasibility.py, read-only).** 8 of 33 carry recordings (class A); 25 are live-tab-only with NO bytes at all (class C — they would need a capture pass in the seat Chrome before any stateless question is even askable).
  - A-HAS-RECORDING (8): chat: cerebras, deepseek, gemini, meta.ai, v0.app, zhipu | video: digen_ai, labs_google.
  - C-LIVE-TAB-ONLY (25): chat: claude.ai, copilot x2, duck.ai, genspark, grok x2, yi_baichuan | video: akool, chatglm, creen, video_digen, video_gemini, giz, video_grok, heygen, video_labs_google x3, magichour, meta, nemovideo, qwen, veoaifree x3.

**3. PER-SEAT STATELESS VERDICTS (combining #1128 re-test evidence + dispatch code + doctrine).**
  - TIER 1 — reachable relatively cheaply: **meta.ai** (class-c capture bug: the live cookie AUTHENTICATES — 200 — the recording is just the wrong request (search doc_id, not chat-send); a re-capture of the actual chat-send in the seat Chrome could make it stateless, caveat: graphql doc_ids rotate on site deploys). **v0.app** (multi-step pipeline: the multistep_replay detect_bootstrap/run_followup infrastructure already exists; capturing the full ack->poll->result sequence as a multi-exchange recording could serve it stateless).
  - TIER 2 — stateless client ALREADY EXISTS but shadowed: **digen_ai**. `digen_session_replay.py::DigenSessionClient` is pure `requests` + Digen-Token from the recording (no Chrome). But `_client_for` checks modality=video + VIDEO_HOSTS -> ChromeVideoClient BEFORE the CLIENTS map (session_pool.py comment: "even hosts with a legacy replay client in CLIENTS (e.g. digen) get the Chrome path when the seat declares modality=video"). The stateless path exists but is deliberately shadowed; graduating it needs token-liveness verification first (read-only check per repo memory: GET /v1/queue/list?status=3 + HEAD sentinel video_url).
  - TIER 3 — redundant: **labs_google (video)** — the same provider's supply is ALREADY served statelessly via the Flow bridge (session_labs_google_flow, FlowApiClient, 103 clips, #1123). The Chrome-backed seat is bonus duplication.
  - TIER 4 — DOCTRINE-BLOCKED from stateless: **deepseek** (x-ds-pow-response proof-of-work) and **zhipu/chatglm** (X-Sign/X-Timestamp/X-Nonce signature). Bridging these in Python means recomputing the provider's PoW/signature ourselves = hand-replaying the provider's protocol = "playing the provider", which BE CHROME forbids (Doctrine 3a: the provider's own JS in real V8 is the contract; we are only the environment). These stay on V8 BY DESIGN, permanently — not for lack of engineering.
  - TIER 5 — rotated bearers, tried-and-reverted: **cerebras, gemini**. Both carry status.replay_graduation='reverted_send_time_gate' — a previous stateless graduation attempt was REVERTED because send-time gates failed. Fresh re-capture might work transiently, but the bearer/gate rotates server-side; expect repeat reverts.
  - TIER 6 — the 25 live-tab-only: no bytes exist. Each needs a capture pass first (capture_sessions_cdp / record_video_job), after which the same tier classification applies. Most video UIs speak websockets/multi-step flows, and recorded_ws seats DELIBERATELY fall through to Chrome (Doctrine 3a) — so most of the 25 will remain Chrome-backed by doctrine even after capture.

**4. BOTTOM LINE.** Full 33->stateless is NOT achievable under the doctrine, and the doctrine is the reason, not a gap: PoW/x-sign seats (deepseek, zhipu) and websocket seats are stateless BY PROHIBITION (hand-replay = copycatting the provider's contract). Realistically reachable stateless graduations: meta.ai (re-capture), v0.app (multi-exchange capture), digen (un-shadow + verify token) — maybe +2-3 seats, all requiring capture/verification work, none free. The 25 live-tab-only seats need capture passes first and will mostly stay V8 anyway. ECONOMICS NOTE: the film runway (110 clips) is already 100% stateless, so V8 expense only affects BONUS supply; and if V8 throughput ever matters, the doctrine-compliant lever is more seat Chromes / headless seat Chromes (still real V8, still Chrome — just more parallel typists), never hand-replay.

**Files added (scratch):** scratch_stateless_feasibility.py.
**Verdict (read-only, nothing changed):** Partially. ~3 seats (meta.ai, v0.app, digen) are realistic stateless candidates with work; 2 (deepseek, zhipu) are permanently V8 by doctrine; 2 (cerebras, gemini) were tried and reverted; labs.google is already stateless via Flow; the 25 live-tab-only seats need capture first and mostly stay V8 by doctrine. The V8 cost is lock-serialization + latency + RAM, not per-execution forking — the browsers are long-lived and Selenium/CDP merely attach.
"""

p = pathlib.Path("MASTER_WORKLOG.md")
t = p.read_text(encoding="utf-8")
if "#1129" in t:
    print("SKIP: #1129 already present")
else:
    if not t.endswith("\n"):
        t += "\n"
    p.write_text(t + ENTRY, encoding="utf-8")
    print("APPENDED #1129. New line count:", (t + ENTRY).count("\n") + 1)
