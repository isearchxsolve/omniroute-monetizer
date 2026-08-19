# OmniRoute-to-Terra Takeover Qualification Plan

## Outcome and non-negotiable constraints

Build and execute an evidence-based qualification campaign proving whether today’s OmniRoute can replace `gpt-5.6-terra/high` for autonomous repository work. The campaign will use **no ChatGPT Plus/Codex-dependent route**, will not disturb live project trees, will not directly edit OmniRoute’s database, will not restart production, and will not claim success from HTTP 200 responses alone.

The first implementation output will be a versioned execution matrix plus a machine-readable run manifest. Execution then advances through explicit gates: instrumentation → independent model qualification → one worker → two workers → four workers → OmniRoute deep dive → final certification.

Every action and result will be appended incrementally to `MASTER_WORKLOG.md` under the next valid numbered entries, with secrets redacted.

## Execution matrix

| Stage | Workload | Concurrency | Route constraint | Required evidence | Gate |
|---|---|---:|---|---|---|
| 0 | Shallow production snapshot | 0 agents | None | Service/version/PID, endpoints, provider+combo hashes, scheduler state, current OAuth state, CPU/RAM, baseline latency | Coherent timestamped snapshot exists |
| 1 | Protocol/capability battery | 1 request stream | No Codex/Plus routes | Non-stream, strict SSE, tool-call+tool-result, JSON, long-context, patch diagnosis, selected model/provider evidence | At least two independent coding-capable routes pass |
| 2 | Deterministic canary benchmark | 1 agent | Dedicated no-Plus benchmark combo | Attempt log, actual route evidence, diff, hidden tests, elapsed time, retries, resource data | Canary passes with no critical regression |
| 3 | Historical Terra replay | 1 agent at a time | No Codex/Plus routes | Clean pre-Terra worktree, leakage scan, visible+hidden tests, blind result comparison | Neon and Crypto deterministic missions pass |
| 4 | Parallel qualification | 2 agents | Provider-diverse no-Plus routing | Per-worker route/latency/tool logs, process state, tests, clean checkpoint/resume | Both finish without retry storm or cross-project interference |
| 5 | Terra-scale qualification | 4 agents | No Codex/Plus routes | Same evidence plus p50/p95 latency, CPU/RAM, queueing, failure distribution, keep-alive observations | Four workers finish or cleanly checkpoint within defined budgets |
| 6 | OmniRoute deep dive | Separate control/load/agent planes | Control plane uses no model | Performance, routing/failover, OAuth, scheduler, persistence, client, recovery reports | No critical mechanics defect; all failures truthfully classified |
| 7 | Final certification | Consolidated | No Codex/Plus routes | Immutable run manifest, benchmark scorecard, strengthened acceptance results | Certified / qualified-with-limits / not-equivalent verdict |

## Phase 1 — Create a coherent qualification framework

1. Add `docs/OMNIROUTE_TERRA_TAKEOVER_MATRIX.md` containing the matrix, decision thresholds, route-independence rule, benchmark scoring rubric, and evidence requirements.
2. Add a declarative fleet manifest under `config/` containing mission ID, project path, goal/benchmark spec, baseline revision, engine, route, timeout, resource class, test commands, concurrency key, and expected artifacts.
3. Add a run-ID-scoped artifact layout under `state/qualification/<run-id>/`; every report from one campaign will share one run ID so stale provider, combo, inference, OAuth, and acceptance artifacts cannot be mixed.
4. Record hashes/snapshots of provider inventory and combo configuration, the OmniRoute version, process identity/start time, and test configuration in `manifest.json`.
5. Never import the old direct-provider launcher’s embedded credential list. The new runner will use only OmniRoute’s local endpoint and environment/DPAPI-backed management authentication.

## Phase 2 — Repair the evidence layer before trusting it

### Acceptance suite

Strengthen `acceptance_tests.py` and its watcher:

- Return a non-zero process exit code for any required failure.
- Treat required skips as non-certifying rather than `MONETIZER_READY`.
- Replace T8’s obsolete Zed check with the requested ZCode provider/schema check.
- Make T9 fail when process uptime evidence is unavailable rather than silently pass.
- Make T10 perform a real repeat-and-compare idempotency assertion on read-only state.
- Make T15 measure the authenticated management endpoint.
- Make T16 report genuine tested provider coverage, not active/total naming.
- Make T17 fail when upstream-verification evidence is absent.
- Make T18 require HTTP 200 and a valid response shape from the intended NVIDIA route.
- Expand T11 secret scanning to operational state/log/report surfaces while excluding encrypted/binary files and known redaction markers.
- Preserve T1–T20 compatibility while adding separate qualification tests for streaming, tools, route identity, and failover rather than disguising a larger suite as the historical 20 tests.

### Provider and OAuth mechanics

- Add per-call timeout support to `OmniRouteAPI.test_connection()` and fix `health_checker.py` to interpret the returned structure instead of treating a non-empty dictionary as healthy.
- Correct `health_watch.py` to use `latencyMs` and to persist explicit active/tested/passed/failed counts.
- Change `oauth_keepalive.py` so individual failures cannot leave the pass marked simply `ok: true`.
- Classify refresh outcomes as:
  - token rotated and expiry advanced;
  - no rotation required but post-refresh provider test remains healthy;
  - degraded/failed.
- Persist pre/post expiry metadata only where already exposed by the supported API, never tokens.
- Add bounded failure history and an alerting verdict without creating refresh storms.

### Protocol qualification

Promote the scratch probes into strict automation modules:

- Streaming: validate HTTP status, SSE content type, `data:` JSON framing, incremental deltas, `[DONE]`, finish reason, TTFT, total latency, and cancellation behavior.
- Tools: require a real `tool_calls` structure, correct function name, valid required JSON arguments, then send a tool result and validate the follow-up response.
- Non-streaming: retain valid payload sizes and capture requested model, response model, latency, and response shape.

## Phase 3 — Establish actual route identity and controlled failover

1. Inspect live response headers and supported management/log APIs for request IDs, effective model, provider slug, connection ID, and route attempts.
2. If native trace metadata exists, persist it for every qualification request.
3. If it does not exist, mark this as an observability gap and prove routing in an isolated sandbox using single-candidate and controlled multi-candidate combos; do not infer the serving provider merely from configured order.
4. Build a dedicated **no-Plus qualification combo** only in the isolated sandbox first. Candidate routes must be individually verified and must exclude `codex/gpt-5.6-sol`, Codex connections, and every ChatGPT Plus-backed provider.
5. Run controlled head failure, fallback success, and all-target failure cases; verify attempt order, retry bounds, delay behavior, selected fallback, and terminal error semantics for ordinary, streaming, and tool-call requests.
6. Only after sandbox proof and a complete production backup may a live no-Plus qualification combo be added through the supported REST API. Existing production combos will not be overwritten for this benchmark.

## Phase 4 — Build the OmniRoute-native fleet runner

Extract the useful orchestration ideas without retaining Codex coupling:

- Add a generic engine-neutral session wrapper with attempt ID, child PID, timestamps, heartbeat, exit code, stop reason, structured status, attempt-specific append-only logs, and optional console retention.
- Add an OmniRoute/Aider engine adapter using the local OpenAI-compatible endpoint. It will target the dedicated no-Plus combo and use repo-map/test execution capabilities already proven by `launch_forest_cli.py`.
- Add a declarative mission registry instead of duplicating project maps across launcher, monitor, autopilot, and resume scripts.
- Add one repository/concurrency lock per Git root so two missions cannot edit the same repository concurrently.
- Use isolated Git worktrees or disposable copies; never reset or edit the current live project trees.
- Record baseline SHA/archive hash, branch/worktree, dirty-state policy, test commands, route, and attempt paths before launch.
- Replace the unsafe broad auto-checkpoint behavior with mission-scoped checkpoint commits in the isolated worktree. Do not stage unrelated user changes, bypass hooks globally, or checkpoint the live branch.
- Add graceful cancellation and process-tree cleanup, plus artifact-based resume from a known checkpoint and project worklog.
- Add a control-plane monitor that does not call an OmniRoute model to decide whether OmniRoute itself is healthy.

## Phase 5 — Construct clean-room benchmarks

### Initial deterministic benchmark set

1. **Neon** from `8d5a24dfd73b20fa12dfd421415c2aaa8fb83d5b`
   - Shared mutable state isolation, safe path handling, atomic writes, and unsupported-stack behavior.
   - Keep live external generation as a separate environmental gate.
2. **Crypto Trader** from `37be8aa158dfd217a427d539af765abb12edadf9`
   - Health observability during delayed initialization, liveness/readiness separation, paper-mode safety, and circuit breakers.
3. **Oioi** from a verified commit before `fdc29df`/`40b6a58`
   - Schema repair under strict free-tier and prohibited-provider constraints.
4. **ASES** only after reconstructing a trustworthy pre-Terra archive or a seeded fixture; current checkpoints already contain Terra work.

For every package:

- Exclude `MASTER_WORKLOG.md`, Terra JSONL/final reports, project `FLEET_WORKLOG.md`, solution-revealing reports, post-run commits, and solution-revealing regression tests from the agent-visible tree.
- Run a leakage scan before launch.
- Keep hidden evaluator tests outside the worker-visible worktree.
- Score correctness, regression avoidance, constraint adherence, autonomy, evidence honesty, scope discipline, elapsed time, request count, retries, and recovery—not raw test-count inflation.

### Deferred benchmarks

- EmergentSH, Ideation, Avatar, and GODSHAND require trustworthy pre-agent archives before clean-room replay.
- OmniRoute’s historical provider-recovery task will use a fixture-backed disposable instance, not live credentials.
- Real Docker, model-generation, OAuth login, Kaggle, and GPU checks remain separately classified environmental gates.

## Phase 6 — Execute capacity gates incrementally

1. Run the protocol battery against individually verified no-Plus routes.
2. Run one small deterministic canary.
3. Run Neon and Crypto sequentially from clean worktrees.
4. If quality gates pass, run two unrelated workers concurrently.
5. If host and routing metrics remain healthy, run four workers to match the old Terra fleet size.
6. During all runs, capture:
   - actual route evidence;
   - request/response protocol validity;
   - TTFT and total latency;
   - CPU, memory, process count, queueing, retries, and errors;
   - provider/OAuth state before and after;
   - diffs, checkpoints, evaluator results, and intervention count.
7. Deliberately terminate one safe canary attempt and verify clean checkpoint resume before four-worker certification.
8. Stop escalation automatically if the control plane detects sustained service degradation, repeated authentication failures, retry storms, cross-project interference, or evidence loss.

## Phase 7 — Dedicated OmniRoute deep-dive pass

Run three separated planes:

- **Control plane:** OS process/scheduler/port/resource collectors and artifact freshness checks; no LLM dependency.
- **Load plane:** bounded latency/concurrency/failover generators with valid payloads.
- **Agent plane:** OmniRoute-backed code-analysis workers examining implementation and automation.

The deep dive will cover:

1. Root/models/providers/combo latency, cold/warm behavior, TTFT, throughput, p50/p95, and concurrency scaling.
2. Combo order, weights, provider IDs, real selection, retries, and failover overhead.
3. OAuth token rotation, expiry advancement, self-managed-token semantics, repeated failures, scheduler cadence, and duplicate-daemon detection.
4. Current Windows Task Scheduler registration, enabled state, last/next run, last result, artifact freshness, and duplicate Python process detection.
5. Provider-native health versus actual inference health reconciliation.
6. Streaming, tool calling, structured output, ordinary chat, and cancellation.
7. ZCode and VS Code configuration validation plus real API-compatible requests using their configured model IDs.
8. Fresh-state behavior on a separate port/data directory, followed by one-by-one artifact replay. Production remains untouched until sandbox reproduction and backup exist.
9. Crash/interruption recovery in the sandbox; no production restart will be initiated.

## Certification rules

OmniRoute will be classified as:

- **Certified Terra replacement:** deterministic replay quality is comparable, no Plus route is used, failover is proven, interruption recovery works, and four workers complete without critical infrastructure degradation.
- **Qualified with limits:** one or two workers are reliable but four-worker capacity or one protocol/mechanics dimension remains degraded.
- **Not equivalent yet:** inference works but repository completion quality, route independence, failover, evidence integrity, or concurrency does not meet the gates.

A successful HTTP response, a configured combo, provider health alone, or a model catalog count will never constitute takeover certification.

## Implementation and execution order after approval

1. Append the planning decision and todo state to `MASTER_WORKLOG.md`.
2. Create the execution-matrix document, manifest schema, and run artifact layout.
3. Implement/fix the evidence layer and its focused tests.
4. Generate the read-only Stage 0 snapshot and report the first real blockers.
5. Build and verify the isolated sandbox and no-Plus qualification combo.
6. Implement the generic runner and single-worker canary.
7. Execute sequential clean-room benchmarks, then two- and four-worker gates only if prior gates pass.
8. Run the OmniRoute mechanics deep dive and strengthened acceptance suite.
9. Produce the final scorecard and append every result to the worklog.

No commit or push will be performed unless explicitly requested after the implementation is reviewed.