import io, time
p = r"d:\omniroute-monetizer\MASTER_WORKLOG.md"
entry = """

---

### [2026-08-28 14:35] #1115 — TRACK 3a: chatx graduated chrome-free via stateless 2-leg replay (LIVE). Transport 20→21/48.

**1. GOAL.** Track 3a was the one solvable send-time gate of the three Track-3 providers (deepseek PoW unsolved, chatglm x-sign unsolved, chatx solvable). chatx.ai is a Laravel app: a single recorded POST /sendchat is NOT enough to replay statelessly because (a) the `_token` is a per-session CSRF that rotates, and (b) the answer is delivered on a SECOND endpoint (GET /chats_stream, SSE) keyed by the conversions_id that /sendchat returns. The prior working flow (scratch_chatx_2leg_replay.py) was Chrome-dependent (Selenium debuggerAddress attach + in-page fetch). Goal: make both legs stateless via curl_cffi and graduate the seat.

**2. SEAT INSPECTION (scratch_chatx_seat.py).** state/secrets/session_chatx.json: host=chatx.ai, modality=chat, cookie_header len=2089 (cf_clearance=...), recorded_exchange = POST https://chatx.ai/sendchat, body fields {_token, user_id=406995736720, chats_id=5313384, prompt=sentinel, current_model=gpt3, is_web=0, is_youtube=0}, headers include X-CSRF-TOKEN + X-Requested-With: XMLHttpRequest.

**3. STATELESS 2-LEG PROOF (scratch_chatx_stateless.py, curl_cffi impersonate="chrome").**
- Leg 0: GET https://chatx.ai/gpt with the seat's cookie_header seeded into the curl_cffi cookiejar → HTTP 200, 391KB page, fresh CSRF extracted from <meta name="csrf-token" content="...">.
- Leg 1: POST /sendchat (form: fresh _token + prompt, X-CSRF-TOKEN + X-Requested-With headers) → HTTP 200 {"response":true,"conversions_id":80096664,"ass_conversions_id":80096665,"quota":{"total":10,"left":10,...}}.
- Leg 2: GET /chats_stream?user_id=&chats_id=&current_model=&conversions_id=&ass_conversions_id=&... (SSE, Accept: text/event-stream) → accumulated type=="response.output_text.delta" deltas → answer "Omni" in 2.7s.
- VERDICT: LIVE (stateless, chrome-free). First run had a bug (curl_cffi Response is not a context manager for stream=True) — fixed to r2 = s.get(..., stream=True) + iter_lines() + r2.close(); legs 0+1 had already proven themselves on run 1.

**4. PRODUCTION CLIENT (scripts/automation/chatx_replay.py, NEW).** ChatXReplayClient matches the pool contract (constructor (secret=path|dict), .chat(messages, model=None, **kw) -> {"text","label","status","raw"}). Per call it runs the full genuine flow: Leg 0 fresh CSRF + cookie refresh → Leg 1 sendchat → Leg 2 SSE. Uses canonical ChatError/SessionExpired imports (never redefines). Guards: NO_CSRF (login wall/layout change), LEG1_REJECTED, NO_CONVERSION_ID, EMPTY_ANSWER, 401/403→SessionExpired("AUTH"), and an _ERR_SIG regex so error text is never counted as an answer. Parallel-safe: each call builds its own curl_cffi Session — no shared browser, no global lock (the exact anti-pattern runtime-Chrome has).

**5. WIRING (scripts/automation/session_pool.py::_client_for).** Inside the graduation lever block (runtime=="replay" + recorded_exchange), added a host check: if "chatx" in host → ChatXReplayClient (before the UniversalSessionClient default). A single-exchange replay cannot serve chatx; the dedicated 2-leg client is the correct transport. Opt-in: only fires for seats that declare runtime="replay".

**6. GRADUATION + POOL VERIFICATION.** scratch_graduate_chatx.py set runtime="replay" + status.alive=True on session_chatx.json. scratch_pool_chatx.py then proved end-to-end through the pool: SessionPool dispatches session_chatx → ChatXReplayClient, and a live call returned text='Omni', label='chatx-2leg-replay'. LIVE through the pool, chrome-free.

**7. TRANSPORT RE-AUDIT (scratch_transport_audit.py).** 21/48 chrome-free at runtime (up from 20). The +1 is chatx (now ChatXReplayClient). 27 seats still Chrome-at-runtime.

**8. DOCTRINE REAFFIRMED.** Chrome = capture/onboard/re-auth/CRUD instrument only. chatx proves the pattern for multi-leg Laravel/CSRF sites: harvest the cookie once (Chrome as capture instrument), then reproduce the full genuine multi-leg flow statelessly with curl_cffi browser-TLS impersonation (Law 4) — fresh CSRF per call, no browser in the request path, parallel-safe.

**9. NEXT (not yet done).**
- Track 1: capture blueprints for the 27 chrome-only seats (Chrome as capture instrument; credit-spending — chat first, video via capture_video_job_cdp.py --dry-run first). Graduate each proven seat.
- cerebras: solve the send-time shape gap (needs the real UI wire request once the consent overlay is cleared).
- gemini: investigate the state-sensitive 401 (may require a fresh in-page send to re-prime the session, or accept Chrome-at-runtime).

**Files created:** scripts/automation/chatx_replay.py (production client), scratch_chatx_seat.py, scratch_chatx_stateless.py, scratch_graduate_chatx.py, scratch_pool_chatx.py.
**Files modified:** scripts/automation/session_pool.py (chatx dispatch in graduation lever).
**Seat files modified (secrets, gitignored):** session_chatx.json (graduated, runtime=replay, alive=True).
**Verdict:** Track 3a delivered 1 clean chrome-free graduation (chatx, LIVE through the pool). Transport: 21/48 chrome-free.
"""
with open(p, "a", encoding="utf-8", newline="\n") as f:
    f.write(entry)
print("appended #1115")
lines = open(p, encoding="utf-8").read().splitlines()
print("total lines now:", len(lines))
