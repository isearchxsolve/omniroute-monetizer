# GLM 5.3 Flash — Current Production Handoff

**Authority.** This is the current operator-approved premise for this repository. Read it after
`TECHNOLOGY_TRANSFER.md`, `CHROME_RULES_FOR_AGENTS.md`, `AGENTS.md`, and the tail of
`MASTER_WORKLOG.md`. It supersedes older handoff sections that say OmniRoute and seat-pool must
never be merged. They are distinct harnesses, but they are intentionally merged at the consumer
endpoint.

## Orchestration authority

The primary orchestrator and final auditor remains the lead Codex agent coordinating this work.
The available credit constraint is on the primary orchestrator, **not on GLM 5.3 Flash**. GLM should
therefore be used as the full-capacity execution worker for the assigned implementation, hardening,
seat-graduation, and verification scope; do not artificially narrow its work because of a supposed
GLM credit cap. GLM must still not redefine this premise, create an unrelated project, alter service
ownership, access the operator's live Chrome profile, promote an inventory row to healthy capacity,
or declare production rollout complete without primary-orchestrator review. Every GLM result must be
returned with exact evidence, failures, changed files, tests, and commit. The primary orchestrator
makes the final health, capacity, graduation, and rollout decision from current evidence.

## Mission

Make and maintain exactly one production consumer surface:

`http://127.0.0.1:8190/v1`

It must be OpenAI-compatible:

- `POST /v1/chat/completions` with `model: "session-pool/auto"` for chat seats;
- `POST /v1/chat/completions` with `model: "video/auto"` for the video lane;
- `POST /v1/chat/completions` with `model: "<host>/auto"` or `video/<host>/auto` for pins;
- `GET /v1/models` for discovery;
- durable video jobs through the existing `/v1/video/jobs` contract.

Use `127.0.0.1`, never `localhost`.

## Original automation premise — do not inflate it into an auth project

The operator's day-one signup request is deliberately narrow: when a provider requires account
creation, automation may drive the ordinary signup UI using an **already-authenticated Google SSO
session** in the approved dedicated automation profile. It must not type or retrieve a Google or
provider password, enter an OTP or email-verification code, defeat CAPTCHA, bypass MFA, or invent a
credential. If the existing SSO session is not already signed in, the correct result is a clearly
reported login/verification wall and a request for the operator to complete that one human step.

Signup is only an onboarding prerequisite. It is not the mission, not a capacity row, and not a
graduation result. After an account exists, the actual work is to make the provider's service work:
capture the legitimate post-signup session or API contract, build the Python runtime adapter, and
prove the provider's real chat/video operation through `:8190`. GLM must spend its execution budget
on provider functionality and video-capacity graduation, not on password/OTP/CAPTCHA automation or
rebuilding signup flows that are not needed.

## Two harnesses, one surface

Keep these implementations and evidence separate:

1. **OmniRoute harness (`:20128`)** — paid/OAuth provider connections and model families. Its
   capacity unit is **provider/account connection × models served**. A model catalog is inventory,
   not proof of live inference or account headroom.
2. **Seat-pool harness (`session_pool.py`, exposed through `:8190`)** — independently captured or
   provider-specific browser/API seats. Its capacity unit is **account/session seat × model family
   or route**, not the number of aliases in a catalog. A Chrome-backed route is a diagnostic/capture
   aid or temporary bridge; it is **not** Chrome-independent Python-adapter capacity.

The final audit must inspect both harnesses together through `:8190`, while preserving the source
of every response (`omniroute`, `session_pool`, or explicit fallback). A fallback must never be
reported as if the originally selected harness answered.

## Capacity accounting rule

Every final matrix row must include:

`harness | provider | account/seat | modality | model family | advertised model IDs | fresh healthy routes | transport | evidence time`

Do not count any of these as serving capacity by themselves:

- a model appearing in `/v1/models`;
- a provider connection marked active;
- a browser capture file marked alive;
- historical replay or graduation evidence;
- a video model name found by keyword search;
- aliases pointing to the same provider/account;
- a successful HTTP status with stale text, a wall, an empty answer, or malformed stream content.

Chat capacity requires a fresh computed response through the real consumer endpoint. Video capacity
requires a **Python-executed**, provider-specific submit → poll → result URL flow, with the completed
result observed and the route admitted only after that proof. A browser may be used only for safe
dedicated-profile observation/capture of the live protocol; it is not an acceptable runtime executor
or graduation substitute. **Chat providers frequently serve video models too.** Treat their video
models as first-class candidates across both OmniRoute and seat-pool evidence; do not silo video work
into only the dedicated-video-seat list. A chat-provider video model becomes graduated video capacity
only when its actual video contract succeeds through the Python adapter.

## Current assigned execution: real Python video-adapter graduation

This is GLM's highest-priority task. The product's binding constraint is durable clip-generation
capacity, not another Chrome-routed alias or an expanded inventory spreadsheet. Build and graduate
real **Python runtime adapters** for video-capable seats, beginning with the existing captured
evidence and stateless/API-capable providers. The runtime must work without an open Chrome tab once
the capture/adapter is complete.

Work in one provider/account/model-family unit at a time:

1. Build the smallest faithful Python transport from the recorded/live protocol: submit, durable
   job identifier, polling/reconciliation, terminal result URL, and response parsing. Reconstruct
   fresh send-time fields where Chrome's own request proves they exist; classify every failure under
   the Chrome Gap Doctrine rather than calling the provider dead.
2. Execute one bounded real generation with the task-owned spend gate and provider cap respected.
   Validate that the terminal URL is downloadable media (not HTML/error JSON; check video bytes such
   as ISO-BMFF `ftyp` where applicable).
3. Prove the same provider through the `:8190` durable `/v1/video/jobs` contract: submit receipt,
   poll/reconcile, terminal completed result. Then admit it as **one** result-verified capacity row.
4. Add each successful model family served by that same provider/account to the capacity matrix as
   `provider/account × models served`; do not falsely count them as independent accounts. Include
   video-capable models hosted by chat providers in this same accounting.
5. On failure, retain an honest evidence row and move to the next independent provider/seat; do not
   spend credits retrying an identical wall/quota/contract failure.

Explicit non-goals: no more Chrome-runtime routing presented as capacity; no synthetic/mock video
result; no model-keyword inventory promoted to capacity; no broad catalog probe; no operator-profile
access; and no alteration of the scheduled-task ownership of `:8190` or `:8189`.

## Non-drift rules

- Do not split the mission into an OmniRoute-only audit and a seat-pool-only audit.
- Do not collapse the two harnesses into one undifferentiated provider count.
- Do not chase the historical 25-chat / 23-video numbers as if they were current facts.
- Do not bulk-probe all OmniRoute catalog models.
- Do not retry a recorded wall, quota, authentication failure, or repeated identical capture failure.
- Do not call a provider dead when Chrome proves it works; classify the gap as send-time transport,
  real server-side wall, or capture bug.
- Do not use the operator's live Chrome profile. Dedicated automation profiles only, with visual
  preflight before DOM actions and post-action verification.
- Do not stop or hand-launch a service owned by a scheduled task. Verify the exact owner and use the
  registered recovery chain.
- Do not declare rollout healthy while `:8190` is absent, while the merged surface has not passed
  its computed smoke probes, or while video has only inventory evidence.

## Current state at handoff

- The endpoint merge and response/fallback code is committed in `57a3534`.
- `session_pool.py` now admits ordinary chat only from the canonical `REPLAY_OK` replay gate. The
  last deterministic check found **11 admitted chat hosts** and **1 video route**; this is not a
  claim that all 11 are currently healthy at this instant.
- OmniRoute last supplied **9,509 advertised model records**. This is a provider/model inventory,
  not 9,509 independent healthy routes.
- Conservative name-family analysis found **103 advertised video-model candidates across 14 owner
  groups**. This is inventory only; it is not 103 accounts, seats, or completed jobs.
- A Law-3 probe exposed malformed OmniRoute output (`5858` where the computed answer is `58`). The
  merged shim contains a narrow numeric duplicate repair, but the final live consumer proof has not
  been rerun.
- The task-owned `:8190` listener has been restored and primary-audited. Cold discovery returned
  9,523 rows with a 9,509-row Omni catalog; `frontier` (OmniRoute) and `session-pool/auto` (Cohere
  seat) each returned the computed `58`. The shim's catalog-refresh timeout and task-log collision
  gaps are committed closed (`0d15676`, `ccd58e0`).

## Exact next sequence

1. Restore `:8190` through the registered `OmniRoute Session Pool Shim (keepalive)` task. Do not
   hand-launch a replacement and do not touch OmniRoute `:20128`.
2. Verify the listener's exact process owner and run only:
   - `GET http://127.0.0.1:8190/v1/models`;
   - computed Law-3 chat on `frontier`;
   - computed Law-3 chat on `session-pool/auto`;
   - one pinned, already admitted chat seat.
3. Record the response source, provider, session, answer, status, and latency. A `200` is not
   healthy unless the computed answer is correct and the response is structurally valid.
4. Build the final provider × model-family × account/seat matrix from those live results plus the
   separate video evidence.
5. Execute the **real Python video-adapter graduation** assignment above. Build from Chrome capture
   only where needed, but accept a provider only after a Python runtime performs submit → poll →
   durable result proof through `:8190`. Sweep dedicated video seats **and video-capable chat
   providers** across both harnesses; account provider/account × every model family served.
6. Commit each component after its test and worklog entry. End with a concise healthy-model audit,
   not a dead-model catalog.

## Required handoff response

Every update must begin with the current outcome, then state:

`live endpoint state | OmniRoute healthy provider/model rows | seat-pool healthy seat rows | video result-verified rows | blockers | next single action`

If a blocker prevents live verification, say **BLOCKED** and stop the sequence there. Do not fill the
missing evidence with historical counts or optimistic labels.
