# OmniRoute-to-Terra Takeover Qualification Matrix

## Purpose
Evidence-based framework to qualify whether today’s OmniRoute can replace `gpt-5.6-terra/high` for autonomous repository work.

## Core Constraints
- **No ChatGPT Plus/Codex-dependent route** may be used for any benchmark or qualification.
- **No mutation** of live project trees, OmniRoute database, or production service.
- **No claiming success** from HTTP 200 responses alone; protocol, tooling, failover, and actual route identity must be validated.
- **Secrets** must be redacted in all logs and artifacts.
- **Incremental worklogging**: every action and result appended to `MASTER_WORKLOG.md`.

## Execution Stages

| Stage | Workload | Concurrency | Route Constraint | Required Evidence | Gate Outcome |
|-------|----------|-------------|------------------|-------------------|--------------|
| **0** | Shallow production snapshot | 0 agents | None | Service/version/PID, endpoints, provider+combo hashes, scheduler state, current OAuth state, CPU/RAM, baseline latency | Coherent timestamped snapshot exists |
| **1** | Protocol/capability battery | 1 request stream | No Codex/Plus routes | Non-stream, strict SSE, tool-call+tool-result, JSON, long-context, patch diagnosis, selected model/provider evidence | ≥2 independent coding-capable routes pass |
| **2** | Deterministic canary benchmark | 1 agent | Dedicated no-Plus benchmark combo | Attempt log, actual route evidence, diff, hidden tests, elapsed time, retries, resource data | Canary passes with no critical regression |
| **3** | Historical Terra replay | 1 agent at a time | No Codex/Plus routes | Clean pre-Terra worktree, leakage scan, visible+hidden tests, blind result comparison | Neon and Crypto deterministic missions pass |
| **4** | Parallel qualification | 2 agents | Provider-diverse no-Plus routing | Per-worker route/latency/tool logs, process state, tests, clean checkpoint/resume | Both finish without retry storm or cross-project interference |
| **5** | Terra-scale qualification | 4 agents | No Codex/Plus routes | Same evidence plus p50/p95 latency, CPU/RAM, queueing, failure distribution, keep-alive observations | Four workers finish or cleanly checkpoint within defined budgets |
| **6** | OmniRoute deep dive | Separate control/load/agent planes | Control plane uses no model | Performance, routing/failover, OAuth, scheduler, persistence, client, recovery reports | No critical mechanics defect; all failures truthfully classified |
| **7** | Final certification | Consolidated | No Codex/Plus routes | Immutable run manifest, benchmark scorecard, strengthened acceptance results | Certified / qualified-with-limits / not-equivalent verdict |

## Decision Thresholds
- **Certified Terra replacement**: All gates pass, four-worker fleet completes without critical infrastructure degradation, and blind review shows comparable code quality.
- **Qualified with limits**: One- or two-worker gates pass but four-worker capacity or one protocol/mechanics dimension remains degraded.
- **Not equivalent yet**: Inference works but repository completion quality, route independence, failover, evidence integrity, or concurrency fails to meet gates.

## Evidence Requirements
- **Actual route identity**: Persist request/response headers, effective model/provider from supported APIs, or controlled sandbox proof.
- **Protocol validity**: Streaming (SSE framing, TTFT, total latency), tools (valid function call + result), non-streaming (standard chat).
- **Failover**: Controlled head failure → healthy fallback with bounded retries and correct error semantics.
- **OAuth mechanics**: Token rotation, expiry advance, scheduler health, no refresh storms, duplicate-daemon detection.
- **Persistence & recovery**: Sandbox reproduction, incremental artifact replay, clean restart, checkpoint/resume from known state.
- **Client integration**: Real ZCode/VS Code requests via configured model IDs, not just config-file presence.
- **Acceptance suite**: Non-zero exit on required failure; required skips do not certify; strengthened T1–T20 as per plan.

## Artifact Layout
All outputs from one campaign share a run ID (`YYYYMMDD-HHMMSS-<git-short>`).

```
state/qualification/<run-id>/
├─ manifest.json          # snapshot of provider/combo/config, version, PID, start time
├─ stage0_snapshot.json   # coarse health, latency, scheduler, OAuth
├─ protocol_battery/
│   ├─ non_stream.jsonl
│   ├─ streaming.jsonl
│   └─ tool_call.jsonl
├─ canary_attempt/
│   ├─ attempt.log
│   ├─ route_evidence.json
│   ├─ diff.patch
│   └─ hidden_test_result.json
├─ historical_replay/
│   ├─ neon/
│   │    ├─ worktree_info.json
│   │    ├─ attempt.log
│   │    ├─ route_evidence.json
│   │    ├─ diff.patch
│   │    └─ hidden_test_result.json
│   └─ crypto/ ... (same structure)
├─ parallel_2workers/
│   ├─ worker_A/
│   │    ├─ attempt.log
│   │    ├─ route_evidence.json
│   │    ├─ cpu_mem_samples.jsonl
│   │    └─ ...
│   └─ worker_B/ ... (same)
├─ four_workers/
│   ├─ worker_*/ ... (same as above)
├─ omnioroute_deepdive/
│   ├─ control/
│   ├─ load/
│   └─ agent/
└─ final_scorecard.json
```

## Implementation Notes
- Use isolated Git worktrees or disposable copies; never edit live project trees.
- Record baseline SHA/archive hash, branch/worktree, dirty-state policy, test commands, route, and attempt paths before launch.
- Replace broad auto-checkpoint behavior with mission-scoped checkpoint commits in isolated worktrees.
- Add graceful cancellation and process-tree cleanup; support artifact-based resume.
- Control plane must not call an OmniRoute model to decide OmniRoute health.

## First Actions (post-approval)
1. Create this matrix document.
2. Log worklog entry for approved plan and matrix creation.
3. Update todo list to reflect progress.

---
*Matrix version: 1.0 — approved 2026-08-19*