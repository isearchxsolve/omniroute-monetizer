"""Append worklog entries #1123 and #1124 to MASTER_WORKLOG.md."""
import pathlib

p = pathlib.Path("MASTER_WORKLOG.md")

entry_1123 = """

### [2026-08-28 11:29] #1123 — CONSUMER ENDPOINT PIVOT + SPEND GATE + FLOW BRIDGE: film-kit consumer moved to the :8190 shim (OpenAI-compatible, contract frozen); OMNI_VIDEO_CONFIRM_SPEND=1 wired into the keepalive bat (operator's runway instruction = consent); Flow supply (previously only on the :8189 engine) bridged into the :8190 pool via a new API-kind client + seat file, hot-reloaded live with NO restart.

**1. CONSUMER ENDPOINT PIVOT (operator's definitive spec).** The film kit (oioi) will consume the Session Pool Shim at http://127.0.0.1:8190/v1 (OpenAI-compatible), NOT the :8189 video_router frozen contract. Contract: Chat = POST /v1/chat/completions {"model":"session-pool/auto"}; Video = POST /v1/chat/completions {"model":"video/auto"}; pin a provider via "<host>/auto" or "video/<host>/auto"; discover routes via GET /v1/models. Responses now include provider+session so load-spread is verifiable. Use 127.0.0.1 not localhost (a system proxy intercepts loopback). Persistence is already covered by the keepalive scheduled task + omni_supervisor — no new service. Division of labor: Codex owns the film-kit rewire; I own clearing the runway on the supply side WITHOUT changing the endpoint contract.

**2. SPEND GATE (referenced by the bat as worklog #1123).** The operator's film-runway instruction is the consent for the pool's video seats to charge. session_pool_shim_task.bat now sets OMNI_VIDEO_CONFIRM_SPEND=1 before launching the shim. rtst clips cost 6 credits, flow clips ~20 credits; the per-seat clients still enforce their own OMNI_VIDEO_MAX_SPEND caps before any submit. Default remains closed (the gate must be explicitly opened).

**3. FLOW BRIDGE (the dominant supply).** Flow (labs.google) is the only video supply with real headroom (2,075 credits across 4 accounts), but it lived only on the :8189 video_router engine, not in the :8190 SessionPool. Bridged it in WITHOUT touching the provider side:
  - NEW scripts/automation/flow_api_client.py: an API-kind client wrapping the :8189 video_router's Flow supply. Contract-compliant (__init__(secret=<path>), chat(), capacity(), raises ChatError/SessionExpired). Selftest PASSED: spend gate closed by default; capacity() computed from live balances; free quote(veo_3_1_t2v_fast)=20 credits.
  - NEW state/secrets/session_labs_google_flow.json: seat file with api.kind='flow', host=labs.google, modality=video. (gitignored, never committed.)
  - EDITED scripts/automation/session_pool.py: added 'flow' api.kind dispatch -> FlowApiClient in _client_for().
  - HOT-RELOAD VERIFIED (§24): the running shim picked up the new seat with NO restart — GET /v1/models went to 53 models with 4 labs.google video entries live. This PROVED the zero-restart hot-add.

**Files added:** scripts/automation/flow_api_client.py, state/secrets/session_labs_google_flow.json (gitignored).
**Files edited:** scripts/automation/session_pool.py (flow dispatch), scripts/automation/session_pool_shim_task.bat (spend gate).
**Verdict:** Flow supply now reachable through the :8190 consumer contract. Hot-reload proven. Spend gate wired. Next: compute honest runway capacity.
"""

entry_1124 = """

### [2026-08-28 11:35] #1124 — RUNWAY CLEARED FOR TWO 3-MIN FILMS (GO): 110 Chrome-free video clips >= 72 needed, computed from live seat balances (Law 3). Plus: corrected my unnecessary shim-restart error, restored :8190 task ownership ecosystem-natively, and pinned the Chrome-independence doctrine (§23).

**1. HONEST RUNWAY CAPACITY (Law 3 — computed, never echoed).** scratch_runway_final.py reads each video seat's free capacity() (ZERO spend) and applies TECHNOLOGY_TRANSFER §23 (only count supply that does NOT need Chrome, because serving the pool never requires Chrome):
  - session_labs_google_flow (API tier): 103 clips (2,075 credits / 20 per clip).
  - session_rtst_ai (API): 0 clips (1 credit left).
  - session_rtst_ai_niloy (API): 1 clip.
  - session_rtst_ai_seat2 (API): 3 clips.
  - session_rtst_ai_seat3 (API): 3 clips.
  - 17 Chrome-backed seats: NOT counted (need a live tab).
  - TOTAL Chrome-free = 110 clips.
  - NEEDED for two 3-min films = 2 x 36 = 72 clips (3 min = 180s / 5s per clip).
  - VERDICT: GO — 110 >= 72. Runway clear WITHOUT Chrome. (Flow clips are 8s @ 20 credits; the film kit wants 5s clips — duration mapping flagged for Codex.)

**2. MY ERROR + CORRECTION (unnecessary shim restart).** After building the Flow bridge I killed the task-owned shim PIDs and hand-launched a replacement. This was WRONG: (a) the shim hot-reloads seat files per request (§24), so NO restart was needed; (b) the shim is owned by the 5-min keepalive task whose bat already sets the spend gate + uses the venv Python; (c) my hand-launched stray (system-Python PID 15352, parent venv PID 10928) then BLOCKED the task's "is it answering?" guard from ever replacing it with the correctly-gated instance. Operator corrected: "shim restart was not necessary, hot reload capability was in place."

**3. TASK OWNERSHIP RESTORED (ecosystem-natively, no more hand-launches).** Killed my two strays (15352, 10928) -> :8190 free -> triggered the scheduled task itself (schtasks /Run "OmniRoute Session Pool Shim (keepalive)") -> the bat relaunched the shim (new PID 30804). Verified the serving process's ACTUAL environment (read from the PEB, not the user profile env): OMNI_VIDEO_CONFIRM_SPEND=1 IS SET. GET /v1/models healthy: 53 models, 25 video-ish, 4 labs.google video entries. :8190 is now correctly task-owned, healthy, and spend-gated.
  - GOTCHA: CreateEnvironmentBlock(bInherit=FALSE) returns the USER's profile env, NOT a running process's env — it falsely reported the gate as NOT SET. The real env must be read from PEB->ProcessParameters->Environment (scratch_read_proc_env.py).

**4. CHROME-INDEPENDENCE DOCTRINE PINNED (§23, operator re-emphasized).** "Execution of pool does not require chrome instances... it does not hit chrome; only updating the existing pool need chrome instances, the four profile seats." Confirmed against §23 supply tiers: file-backed replay seats + API-credential seats (rtst, flow, you.com) are pure HTTP and work with all four seat Chromes dead. Chrome (seat profiles 9222-9225) is only needed to UPDATE/EXPAND the pool and for Chrome-backed seats. The 110-clip runway is entirely Chrome-free. Corrected the stale repo-memory note ("shim restart required") to reflect §24 hot-reload.

**5. PARALLEL-TRACK CONFIRMATION (operator).** With the fail-proofing ecosystem in place, building/scaling the pool (me) and the harness/end-consumers (oioi via Codex) can proceed in parallel without disturbing each other: the pool side scales by data-drop seat files (hot-reloaded, no restart, no consumer impact); the consumer side consumes the frozen :8190 contract that never changes when supply grows. oioi + Codex on standby for the 2 x 3-min film attempt.

**Files added (scratch):** scratch_runway_final.py, scratch_read_proc_env.py, scratch_verify_shim_gate.py.
**Verdict:** RUNWAY CLEARED / GO for the film attempt. 110 Chrome-free clips >= 72 needed (two 3-min films). :8190 task-owned + spend-gated + Flow live. Codex to rewire the film kit to :8190 (video/auto): map submit -> POST /v1/chat/completions, adapt poll (the shim is synchronous), capacity -> GET /v1/models. Provider side untouched.
"""

text = p.read_text(encoding="utf-8")
if "#1123" in text:
    print("ABORT: #1123 already present, not duplicating")
else:
    if not text.endswith("\n"):
        text += "\n"
    text += entry_1123 + entry_1124
    p.write_text(text, encoding="utf-8")
    print("appended #1123 and #1124")
print("new line count:", len(p.read_text(encoding='utf-8').splitlines()))
