# OmniRoute Monetizer — Capacity Matrix

**Generated:** 2026-08-30 13:05 UTC (live state, not memory); **updated 2026-08-30 20:45 local** by the GLM 5.3 Flash session (worklog #1367–#1368).
**Sources:** `state/replay_check.json`, `state/graduation_ledger.json`, `state/profile1_reconciliation.json`, `state/video_capability_matrix.json`, `state/video_route_inventory.json`, `state/video_dedicated_profile_preflight.json`, live OmniRoute `:20128` and consumer `:8190` probes, `state/merged_healthy_capacity_audit.json`.

---

## 1. Chat Capacity

### 1.1 OmniRoute Core (`:20128`)
- **9,509 models** exposed via `GET /v1/models`.

### 1.2 Canonical Jar-Replay Gate
Source: `state/replay_check.json` (25 seats).

| Verdict | Count |
|---------|-------|
| **REPLAY_OK** | **11** |
| NO_ANSWER | 7 |
| AUTH | 4 |
| WALL | 3 |

**REPLAY_OK hosts (11):**
`api.1min.ai`, `api.cohere.com`, `api.groq.com`, `chat.deepseek.com`, `chat.mistral.ai`, `chat.qwen.ai`, `chatgpt.com`, `claude.ai`, `felo.ai`, `veoaifree.com`, `www.perplexity.ai`

### 1.3 Graduation Ledger
Source: `state/graduation_ledger.json` (34 seats).

| Verdict | Count |
|---------|-------|
| REPLAY_OK | 10 |
| FAIL | 12 |
| NO_ANSWER | 6 |
| WALL | 3 |
| AUTH | 2 |
| UNPARSEABLE | 1 |

**REPLAY_OK (10):** 1min.AI, Claude Official Web, Cohere Coral Web, DeepSeek Chat, Felo AI Web, Genspark AI, Groq Chat, Mistral Le Chat, Perplexity Free Web, Qwen Chat (Alibaba).

### 1.4 Live-Tab Adapter Lane
These providers are Chrome-gated (client-minted anti-bot tokens / SDK sessions) and cannot be jar-replayed. Each is graduated by driving the seat Chrome (`:9222`) composer directly. **Verified by arithmetic probe `41 + 17` → computed `58` (Law 3, not echoable).**

| Provider | Status | Mechanism | Proof |
|----------|--------|-----------|-------|
| **Copilot** | ✅ Graduated | CDP live-tab DOM reader | 58 |
| **Puter** | ✅ Graduated | In-page `puter.ai.chat()` SDK | 58 |
| **V0** | ⏸ Throttled | CDP live-tab composer + poll | 58 proven; account 429-throttled, re-run after decay |
| **Gemini** | 🔧 In progress | Send works (network confirmed); response read TBD | — |

### 1.5 Consumer Endpoint (`:8190`) — what the film kit calls
Base URL: `http://127.0.0.1:8190/v1`
- **9,522 models** exposed via `GET /v1/models` (9,509 OmniRoute inventory rows + 10 admitted chat pins + `session-pool/auto` + `video/auto` + `video/labs.google/auto`).
- Chat admission: only canonical `state/replay_check.json` `REPLAY_OK` hosts are admitted (#1361 hardening); `poe.com` correctly excluded.
- Video lane: `video/auto` and `video/labs.google/auto` routes are served on the shim and the async `/v1/video/jobs` contract is present; no video spend or result-proof this session.
- Listener ownership: the registered `OmniRoute Session Pool Shim (keepalive)` task only. The owning bat now carries a verify-and-retry start that survives an exclusively-locked log file — the cause of the hours-long silent `:8190` absence earlier this day (`a19542c`, worklog #1367).

### 1.6 Profile-1 Reconciliation
Source: `state/profile1_reconciliation.json` (51 seats).

| Status | Count |
|--------|-------|
| PENDING_EVIDENCE | 21 |
| FAIL | 13 |
| REPLAY_OK | 6 |
| NO_ANSWER | 5 |
| WALL | 3 |
| AUTH | 2 |
| UNPARSEABLE | 1 |

---

## 2. Video Capacity

### 2.1 Video Providers
Source: `state/video_capability_matrix.json` — **22 providers**:

qwen-cloud-token-plan, bailian-coding-plan, vertex (vertex-veo), googleflow (google-flow), kie (kie-video), haiper (haiper-video), leonardo (leonardo-video), pollinations (pollinations-video), minimax (minimax-video), together (together-video), replicate (replicate-video), comfyui + 10 more.

### 2.2 Video Route Inventory
Source: `state/video_route_inventory.json` — **59 total video routes** (ainative provider head).

### 2.3 Dedicated Video Profile
Source: `state/video_dedicated_profile_preflight.json`:
- Providers: `[digen, flow, rtst]`
- **5 enabled accounts** across 3 dedicated profiles: `providers`, `seat2`, `seat3`.
- Preflight status: Chrome not currently open, no job quoted, no job submitted.

---

## 3. Session This Stretch (post power-trip, 2026-08-30)

| # | Provider | Outcome | Commit |
|---|----------|---------|--------|
| 1 | Copilot | ✅ Graduated (live-tab DOM reader, 58) | `4754baf` |
| 2 | Aymo | Closed — paywall (429 body = "Credit limit exceeded", decay-retry disproven) | `5a5450c` |
| 3 | Puter | ✅ Graduated (puter.js SDK, 58) | `6346d89` |
| 4 | Poe | ✅ Graduated (gql_POST REPLAY_OK, pre-existing seat) | `c8131ae` |
| 5 | Monica | ✅ Graduated (deterministic prompt surgery + coherent id rotation, REPLAY_OK) | `c82ea46` |
| 6 | V0 | ⏸ Adapter built + proven (58); account 429-throttled | `f59902e` |
| 7 | DeepSeek, Cohere, Qwen, Claude.ai | ✅ Graduated stateless (`runtime:replay` lever pulled for the first time; computed 58; no Chrome in the request path) | `a19542c` |

---

## 4. Honest Classifications

- **Not dead, not "rate-limited into the grave":** Every failure this session was classified against the three-cause doctrine with evidence. Aymo's 429 was re-probed after a decay window and reclassified from "transient" to "credit-limit paywall" — that is why decay-retry is not a universal fix.
- **Chrome-gated ≠ dead:** Copilot/Puter/V0/Gemini all fail jar-replay because the browser mints a per-send token. Driving the browser's own composer is the sanctioned fix (operator override #110), not credential invention.
- **V0 429:** a real throttle on rapid automated sends, not a site death. Adapter is correct; re-run after the window decays.
- **No fabricated credentials:** every graduated host is verified with a computed (Law-3) probe, never an echoable keyword.

---

## 5. Stateless graduation pass (2026-08-30 ~20:45 local) — worklog #1368

The task-owned `:8190` was restored after hours of silent absence: a foreign process held an exclusive
handle on `logs/shim_stdout_current.log`; cmd aborts the start line silently when a redirect open fails
(errorlevel stays 0 — measured), so the task reported 0 every 5 minutes without ever launching the shim.
Fix: verify-and-retry start in the owning bat (attempt 1 → listener probe → retry on `shim_stdout_alt.log`).
Commit `a19542c`. No hand-launch was used; ownership intact.

The #1113 graduation lever (`"runtime": "replay"` in the seat file) was pulled for the first time,
serially, one computed Law-3 probe per seat (41 + 17 → 58), keep on pass, revert on fail:

| Seat | Transport after lever | HTTP | Latency | Answer | Verdict |
|---|---|---|---|---|---|
| chat.deepseek.com | stateless replay + Node PoW (§26) | 200 | 14.9s | 58 | **KEPT** |
| api.cohere.com | stateless replay | 200 | 1.3s | 58 | **KEPT** |
| chat.qwen.ai | stateless replay | 200 | 4.9s | 58 | **KEPT** |
| claude.ai | stateless replay | 200 | 2.4s | 58 | **KEPT** |
| api.1min.ai | stateless replay | 200 | 3.1s | prose-wrapped, not clean 58 | reverted |
| chatgpt.com | stateless replay | 500 | 0.4s | UNPARSEABLE 4557B (firewall held) | reverted |
| www.perplexity.ai | stateless replay | 200 | 2.8s | 58 + search-content pollution | reverted |

**Chrome-independent chat supply now serving: 4 verified stateless seats + the OmniRoute plane.**
`session-pool/auto` re-probed after the pass: 200 in 7.1s, `58`, served by a stateless seat.

Transport classifications (no lever pulled, no wasted probes):
- **api.groq.com** — auth is a short-lived Stytch JWT minted in-page (§18.4); stateless file replay cannot harvest it. In-browser transport only.
- **chat.mistral.ai** — bootstrap-then-second-stream exchange (§6, §18.3); resolved in-browser only.
- **felo.ai** — 2-leg SSE flow (§18.5); no stateless client exists for it (the chatx 2-leg client is chatx-specific).
- **veoaifree.com** — class-(b) quota death, operator-verified in Chrome (§18.6); its stale gate REPLAY_OK is not acted on and not retried (no-hammering rule).

Audit artifact: `state/merged_healthy_capacity_audit.json` (merged_advertised=9522, omni_inventory=9509, seat_chat=10, seat_video=1; verified routes: `frontier` healthy via omniroute 251ms, `session-pool/auto` healthy via stateless deepseek 12.5s).

---

## 6. Python video-adapter graduation sweep (2026-08-30 ~21:15-21:45 local) — worklog #1369

Revised-handover assignment: real **Python-executed** submit -> durable job -> poll -> result
proof through `:8190`'s `/v1/video/jobs` durable contract; browser only for dedicated-profile
observation/capture. One provider/account/model-family unit at a time; one bounded generation
per unit; honest evidence row on failure, no retry of a wall.

**Adapter components committed this sweep** (dispatch on seat-file `api.kind`, spend gate
`OMNI_VIDEO_CONFIRM_SPEND` + `OMNI_VIDEO_MAX_SPEND`, submit-exactly-once, ledger-before-poll):
`scripts/automation/kie_video_client.py` (KIE Market createTask/recordInfo) and
`scripts/automation/aistudio_video_client.py` (Gemini API Veo predictLongRunning). Seat files
`session_kie_ai.json` / `session_aistudio_veo.json` written from VERIFIED vault keys (gitignored,
keys never printed).

| Unit (provider/account/family) | Python transport proof | Bounded generation result | Classification |
|---|---|---|---|
| kie.ai / vault key / kling-3.0 | createTask + recordInfo clients live; selftest 15/15; wallet read 7.79 | createTask refused: "Credits insufficient" (HTTP 402-class); **0.0 spent**; durable row `kie-grad-001` = failed/wall | **wall: wallet balance** (unit mismatch lesson: the measured 35-credits sample beat the doc-schema 1.23 placeholder; 7.79 < any clip) |
| aistudio.google.com / vault key / veo-3.1-fast | ListModels 200 shows veo-3.1/-fast/-lite predictLongRunning; selftest 10/10 | predictLongRunning HTTP 429 RESOURCE_EXHAUSTED ("exceeded your current quota... billing"); **0.0 spent**; durable row `aistudio-veo-grad-001` = failed/wall | **wall: quota/billing** (key sees Veo; project has no generation quota) |
| rtst.ai / rtst-1 / ltx25pro family | RtstApiClient free reads live: balance 1.0, menu + quotes parsed (cheapest vidu 3s@540p = 6.0) | no submit attempted: `can_afford` false at 1.0 balance | **wall: wallet balance** (stale "11 credits" from 2026-08-27 gone) |
| segmind / vault key / (5 video ids) | get-user-credits 200 | balance 0.0 + free-credits 0.0 -> nothing spendable | **wall: empty wallet** |
| pollinations / no key / 17 video ids (wan, seedance, grok-video, veo, nova-reel...) | keyless model discovery 200; docs contract captured (GET /video/{prompt} -> video/mp4) | generation requires Bearer key; ALL video models paid_only (Pollen); no key in vault | **wall: no account/key** (signup = harvest-agent territory, Law 5) |
| novita, deepinfra, veoaifree | prior evidence | 403 NOT_ENOUGH_BALANCE / 402 / quota death | **walls, not retried** (no-hammering rule) |

**Durable-contract proof achieved (independent of the walls):** both `:8190` submissions returned
an immediate **202 durable receipt** (idempotent `job_key`, provider/session attribution), the
worker thread executed the Python client, the terminal failure state is durable and queryable via
`GET /v1/video/jobs/{id}`, and **zero credits were spent on any refusal**. The consumer contract
and the adapter discipline work; the missing ingredient everywhere is **account headroom**.

**What is NOT claimed:** no video capacity row is graduated this sweep — a completed
result-verified row requires an actual MP4 (`ftyp`-checked) through the contract, and every unit
with a live verified credential is walled on money/quota. Transport-side, the pool now dispatches
`api.kind` = rtst/youcom/flow/digen/**kie**/**aistudio** statelessly.

**Unblock paths (operator/orchestrator decisions, not agent work):** (a) top up ANY one wallet
(kie 7.79 credits in wallet; cheapest observed clip ~35 credits) and the SAME committed adapters
produce a result-verified row with one bounded generation; (b) authorize the dedicated-profile
capture of a Google Flow job exchange (2,075-credit supply, tabs already open on 9222/9224/9225)
to build the pure-Python Flow adapter — the largest stateless video prize available.
