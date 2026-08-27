import pathlib
p = pathlib.Path("MASTER_WORKLOG.md")
entry = """

**ADDENDUM to #1113 — LIVE VERIFICATION + FIRST GRADUATIONS + CONCURRENCY PROOF (same session):**

**7. LIVE VERIFICATION of graduation candidates (one call each, stateless replay, NO Chrome):**
- api.groq.com → AUTH-EXPIRED (invalid or expired jwt) — transport reached the API cleanly (curl_cffi TLS accepted), credential just stale → re-auth case.
- chat.cerebras.ai → AUTH-EXPIRED (Unauthorized).
- chat.deepseek.com → GATE: body was `{"code":40301,"msg":"INVALID_POW_RESPONSE"}` — a Proof-of-Work send-time gap (Chrome Gap Doctrine cause (a): fixable, the site adds a PoW at send-time not in the recorded bytes). NOT a live success.
- chat.mistral.ai → **LIVE** (13.6s, answered "ready"). FIRST clean stateless success.
- chat.qwen.ai → **LIVE** (3.7s). api.cohere.com → **LIVE** (1.0s). felo.ai → **LIVE** (16.4s). api.1min.ai → **LIVE** (2.9s). www.perplexity.ai → **LIVE** (3.1s).
- gemini.google.com → AUTH-EXPIRED (401 in Bard's batched envelope).
- chatglm.cn → HTTP 400; chatx.ai → HTTP 419 (send-time gaps, cause (a)).

**8. FIRST GRADUATIONS — 6 chat seats moved OFF runtime-Chrome onto stateless replay:**
Set `"runtime": "replay"` in the seat files for: chat.mistral.ai, chat.qwen.ai, api.cohere.com, felo.ai, api.1min.ai, www.perplexity.ai. Verified the pool now dispatches all 6 to `UniversalSessionClient` (not ChromeReplayClient). Pool-wide stateless-replay seats went 8 → 12. (qwen's VIDEO seat correctly stays on ChromeVideoClient — modality=video, different path.)

**9. CONCURRENCY PROOF — the exact anti-pattern the operator flagged, now resolved:**
Fired 6 PARALLEL chat calls at graduated stateless seats (scratch_concurrency_proof.py):
- peak simultaneous in-flight: **6** (all overlapped);
- wall-clock: **6.4s** vs **16.9s** if serialized → **2.7x speedup**;
- VERDICT: CONCURRENT — no driver-lock serialization. Under the old runtime-Chrome path these 6 calls would have queued behind `_DRIVER_LOCK` (one browser, one typist) and taken >= sum sequentially. Stateless replay parallelizes cleanly.

**10. DISPOSITION of the 12 statically-ready seats after live verification:**
- GRADUATED (6): mistral, qwen, cohere, felo, 1min, perplexity.
- AUTH-EXPIRED → need Chrome re-auth, then re-verify (3): groq, cerebras, gemini.
- SEND-TIME GATE → fixable cause-(a) gaps, need send-time field reconstruction (3): deepseek (PoW), chatglm (400), chatx (419).

**Doctrine now operational:** Chrome = capture / onboard / re-auth instrument. Runtime serving = stateless HTTP replay (curl_cffi) for any seat with a proven blueprint + live cookie. The breadth-not-depth spreader can now actually spread concurrent load.

**Files created (scratch):** scratch_live_replay_one.py, scratch_live_replay_sweep.py, scratch_live_replay_sweep2.py, scratch_live_replay_sweep3.py, scratch_concurrency_proof.py, scratch_append_1113.py
**Seat files modified (graduated):** session_mistral_le_chat.json, session_qwen_chat_(alibaba).json, session_cohere_coral_web.json, session_felo_ai_web.json, session_1min_ai.json, session_perplexity_free_web.json
"""
with open(p, "a", encoding="utf-8", newline="\n") as f:
    f.write(entry)
print("appended #1113 addendum, total lines:", len(p.read_text(encoding='utf-8').splitlines()))
