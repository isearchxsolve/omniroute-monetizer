# GLM 5.3 Flash — Current Production Handoff

**Authority.** This is the current operator-approved premise for this repository. Read it after
`TECHNOLOGY_TRANSFER.md`, `CHROME_RULES_FOR_AGENTS.md`, `AGENTS.md`, and the tail of
`MASTER_WORKLOG.md`. It supersedes older handoff sections that say OmniRoute and seat-pool must
never be merged. They are distinct harnesses, but they are intentionally merged at the consumer
endpoint.

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

## Two harnesses, one surface

Keep these implementations and evidence separate:

1. **OmniRoute harness (`:20128`)** — paid/OAuth provider connections and model families. Its
   capacity unit is **provider/account connection × models served**. A model catalog is inventory,
   not proof of live inference or account headroom.
2. **Seat-pool harness (`session_pool.py`, exposed through `:8190`)** — independently captured or
   provider-specific browser/API seats. Its capacity unit is **account/session seat × model family
   or route**, not the number of aliases in a catalog.

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
requires the correct provider-specific submit → poll → result URL flow, with the completed result
observed and the route admitted only after that proof. Chat providers that expose video models must
appear in the video inventory, but they do not become graduated video capacity until their actual
video contract succeeds.

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
- The task-owned `:8190` listener is currently absent after recovery attempts. This is the immediate
  blocker. Do not proceed to broad audits or video spending until it is restored.

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
5. Graduate Profile-1 seats serially through the transport Chrome actually uses. Use dry-run and
   visual/auth checks first. Video is admitted only after submit → poll → result proof; never count
   a Python replay skeleton or a model-name inventory as graduation.
6. Commit each component after its test and worklog entry. End with a concise healthy-model audit,
   not a dead-model catalog.

## Required handoff response

Every update must begin with the current outcome, then state:

`live endpoint state | OmniRoute healthy provider/model rows | seat-pool healthy seat rows | video result-verified rows | blockers | next single action`

If a blocker prevents live verification, say **BLOCKED** and stop the sequence there. Do not fill the
missing evidence with historical counts or optimistic labels.
