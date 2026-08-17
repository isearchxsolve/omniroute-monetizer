# OmniRoute Fleet Worklog

### [step 1] Session started and prior context restored
- Read `MASTER_WORKLOG.md` as required by repository instructions; it records the current 296-provider ledger baseline and prior 20/20 certification.
- Confirmed `FLEET_WORKLOG.md` did not yet exist. No prohibited credential, environment, wallet, or authentication files were accessed.
- Next: perform an all-connection shallow API and script inventory audit.

### [step 2] Initial inventory command limitation
- The initial non-mutating inventory command listed the repository root successfully; `rg` is unavailable in this PowerShell environment (`The term 'rg' is not recognized`).
- This is an environment limitation only; subsequent discovery will use PowerShell's native recursive file enumeration without touching `scratch/` evidence files unnecessarily.
- Next: locate safe management/probe scripts and query the full provider inventory.

### [step 3] Ledger scope and supported automation identified
- Parsed `state/all_296_providers_execution_ledger.json` without accessing any prohibited secret source: 16 `CONFIGURED_INACTIVE`, 6 `LOCAL_OR_PUBLIC`, 22 `LIVE_ACTIVE`, 10 `CASCADE_ROUTED`, and 14 `BLOCKED_*` catalog entries.
- Identified the existing native OAuth refresh path (`scripts/automation/oauth_keepalive.py --once`) and the zero-auth provisioner. The provisioner must not be run blindly because it contains seven generic slugs while the ledger's six candidates are specific local endpoints.
- Next: run one native OAuth refresh pass; it will authenticate through the established secure management mechanism and emit only redacted result metadata.

### [step 4] Native OAuth refresh completed across the full live connection set
- `python scripts/automation/oauth_keepalive.py --once` logged into the management API and established the current ground truth: `GET /api/providers` returned **56 total connections** (the prior ledger's 51 is stale).
- Refresh results: HTTP-successful native refresh for `kimi-coding`, `kiro`, `amazon-q`, and the newer `codex` connection; `github` and `kilocode` failed with `Token refresh failed — provider returned no new token`. No credential values were emitted or recorded.
- Next: capture a sanitized all-56 connection inventory, then test/re-enable the exact inactive rows with valid inference probes rather than relying only on connection health checks.

### [step 5] Non-mutating metadata inspection command error
- A PowerShell formatting expression used an invalid inline `if` form, producing `The term 'if' is not recognized`; no file or OmniRoute state was changed.
- The same invocation did successfully identify the existing bulk model/test and coverage helpers. The metadata query will be reissued with valid syntax.
- Next: use a purpose-built redacted REST audit to avoid ambiguous raw output and obtain model-to-provider mappings.

### [step 6] Full redacted REST audit of all 56 connections
- Added and ran `scripts/automation/fleet_provider_audit.py`; it queried every connection through `GET /api/providers` and `POST /api/providers/{id}/test`, persisting only sanitized fields to `state/fleet_provider_audit.json` (no API-key, token, cookie, or password fields).
- Result: 22 active / 34 inactive connection rows; 27 valid connection tests. Of the inactive rows, only `lmarena` had a present credential **and** a valid test (HTTP 200, 818 ms). `openai` had a present credential but returned `Invalid API key`; all other inactive candidates lacked a viable credential/session or returned their documented auth/paywall/runtime wall.
- Decision: targeted reactivation is restricted to connections that have both an existing credential and a valid health result; this prevents activating the objectively dead OpenAI key. Next: reactivate `lmarena` through PUT, then identify its and other providers' model routes for valid standard-chat inference probes.

### [step 7] First configured-inactive provider revived
- Re-ran the redacted auditor with targeted recovery. `PUT /api/providers/54efdf9f-8f7c-4c68-b461-12714e89c754` enabled the valid LM Arena connection (HTTP 200); its post-change native test also returned HTTP 200 / valid / 593 ms.
- The all-connection audit count moved from 34 to 33 inactive rows. `/v1/models` is reachable and currently returns 3,277 model IDs, including 173 LM Arena-owned routes.
- Correction before the wider reactivation pass: OAuth credentials reside in protected provider metadata, not necessarily the `apiKey` field. The recovery guard is therefore `test.valid == true` rather than `hasCredential`; this identifies valid disabled OAuth rows without exposing their metadata.
- Next: re-enable every remaining disabled connection whose upstream test is valid, then prove each recovered/direct/cascade route through valid chat-completion calls.

### [step 8] Five additional valid disabled connections revived
- The valid-test-gated recovery pass issued five supported `PUT /api/providers/{id}` updates, all HTTP 200 with an immediate valid post-update test: `clinepass`, `grok-cli`, `agy`, and two `antigravity` connections.
- The all-connection state is now 28 active / 28 inactive. Disabled rows that return `reauth_required`, `missing_api_key`, `Invalid API key`, HTTP 402, unsupported validation, or missing local runtime remain disabled; none were guessed or force-enabled.
- Added `scripts/automation/fleet_inference_audit.py`, which uses the public OmniRoute inference endpoint and a standard `max_tokens=16` chat payload. It stores only model ID, HTTP status, latency, and response-shape validity in `state/fleet_inference_audit.json`.
- Next: execute the direct-provider and cascade inference sweep (up to one retry model per route), then classify failures from actual HTTP evidence.

### [step 9] First standard-chat inference sweep completed — 26/36 routes verified
- `fleet_inference_audit.py` sent valid non-streaming chat completions (`max_tokens=16`, normal user prompt) across 26 direct/cascade routes concurrently. **26 returned HTTP 200 with an OpenAI-compatible `choices` response**; evidence and latency are in `state/fleet_inference_audit.json`.
- Direct failures after up to three catalog-model attempts: `amazon-q` (404), `clinepass` (401), `lmarena` (401 despite its native health check), `nara` (404), `openrouter` (404), and `zai-web` (502). Cascade failures: `auto/claude-sonnet` timeout, `auto/best-chat` 503, `auto/best-coding` 503, and `auto/pro-reasoning` 503.
- This command intentionally exited non-zero because failures are present (`total=36 valid=26 failed=10`); the failure is recorded as evidence, not treated as success. Added targeted probe options and per-attempt evidence for a single repair/retest cycle.
- Next: retest the six failed direct providers once with fresh catalog candidates and inspect/update only the four failed combo routes through the management API.

### [step 10] One repair cycle confirms six direct routes are not inference-live
- Fresh catalog retry evidence in `state/fleet_inference_repair.json`: Amazon Q returned 404 for both published aliases; LM Arena returned 401 for three candidates; Nara returned 400/404; OpenRouter returned 404; Z.ai Web returned 405; ClinePass no longer published a matching catalog owner after its earlier 401 attempt.
- These are valid standard chat-completion attempts, not provider-test assumptions. The retry run exited non-zero (`total=16 valid=8 failed=8`); six direct failures are conclusive after the permitted repair cycle. Two cascade aliases (`auto/claude-sonnet`, `auto/best-fast`) hit a 60-second timeout; four initially transient 503 cascades recovered to HTTP 200 on this retry.
- Sanitized combo audit confirms 13 named combos and shows that the affected `auto/best-*`, `auto/pro-*`, `frontier`, `kimi-coding`, and `moonshotai/kimi-k3-free` combos are backed by the currently verified NVIDIA head; no blind combo mutation is warranted for transient successes.
- Next: demote the six inference-failed direct connections via REST, rerun the all-connection audit, and use the existing browser/session machinery on the three specifically session/auth-blocked catalog providers.

### [step 11] Resumed pending fleet automation from existing evidence
- Read the append-only fleet feed and the required master history; the prior session completed the valid-test-gated revival of six disabled connections and one standard-chat repair cycle, but had not yet performed the planned demotion, ledger regeneration, or final certification.
- Shallow inspection confirmed the repository contains dedicated redacted audit, inference, combo, demotion, zero-auth, and OAuth-refresh management scripts. `rg` is unavailable in this PowerShell environment, so native PowerShell enumeration will be used.
- Next: determine whether OmniRoute on :20128 is currently reachable, inspect only redacted ledger metadata, and continue from the persisted evidence without accessing prohibited credential files.

### [step 12] Current-service shallow health check found management-plane timeouts
- `GET /` returned HTTP 200, while `GET /v1/models` exceeded an 8-second request timeout. The persisted ledger remains stale at 16 `CONFIGURED_INACTIVE` entries despite the prior REST reactivations.
- The supported `fleet_demote_unverified.py` recovery operation could not start because management login to `localhost:20128` timed out after 15 seconds (`requests.exceptions.ReadTimeout`); no provider update occurred and no demotion file was produced by this failed run.
- Next: establish the process/log-level cause of the intermittent management timeout before retrying any mutation; preserve the prior inference evidence and do not bypass the REST API.

### [step 13] Shallow host evidence points to a saturated OmniRoute Node process
- `Get-NetTCPConnection` found one listener on `0.0.0.0:20128` (PID 19028, `node`) with approximately 2.41 GB working-set memory. The same process served `/` but stalled management/model requests.
- The first recent-log enumeration itself exceeded the 30-second shell limit after process inspection; no logs were altered and no restart was performed. This is consistent with the current service/resource saturation, not evidence of a provider credential issue.
- Next: consult upstream/public symptom sources as required, then choose the least invasive recovery supported by evidence. No production state will be changed until the management API is responsive.

### [step 14] External-source triangulation completed before deeper runtime action
- Consulted the upstream OmniRoute repository and public API documentation: management connection changes are supported through authenticated `/api/providers` endpoints, matching this project’s REST-only constraint; the project is a Node/Next.js gateway backed by SQLite/WAL.
- A current OmniRoute client integration notes that a live `/v1/models` catalog should be cached for at least 60 seconds to avoid compaction hangs. This accords with local evidence (root responsive, model/management plane stalled) but is an inference, not a proven root cause.
- Next: retry the shallow health endpoints after the saturation window and only resume provider work if management login returns. Sources consulted: GitHub `diegosouzapw/OmniRoute`; public `omni-providers` API skill; OpenCode OmniRoute plugin documentation/search results.

### [step 15] Service recovered without intervention; full REST audit can safely resume
- Follow-up checks recovered naturally: `/` returned HTTP 200 in 1,982 ms and `/v1/models` returned HTTP 200 in 4,426 ms (1,258,239 bytes). `/api/health` returned HTTP 401 in 2,506 ms, which confirms the protected management plane is answering rather than timing out.
- The OmniRoute Node working set had fallen from ~2.41 GB to ~1.86 GB. No restart, database action, or credential change was made.
- Next: run the existing redacted all-connection REST test with its valid-test-gated reactivation rule, then separately prove all resulting active routes with standard chat completions.

### [step 16] Full all-connection REST audit completed; no additional safe reactivations
- `python scripts/automation/fleet_provider_audit.py --reactivate-inactive` completed successfully: management login OK, **56 total connections**, **27 valid upstream tests**, **28 inactive after the valid-test-gated pass**. No further disabled row met the rule for reactivation.
- The remaining configured-inactive rows now have redacted, exact native diagnoses in `state/fleet_provider_audit.json` (missing/invalid API key, expired OAuth refresh token, unsupported validation, missing local CLI runtime, required web cookie, or HTTP 402), rather than being treated as candidates for guessed credentials.
- Next: execute the previously staged demotion of six direct routes disproven by standard-chat retries, then re-run the complete active/cascade standard-chat sweep.

### [step 17] All six local/public candidates lack a local serving runtime
- Read-only probes to the advertised local OpenAI/Ollama endpoints for Ollama/g4f-Ollama, oobabooga, vLLM, LM Studio, and LocalAI all failed with `Unable to connect to the remote server` (each within ~2.3–2.7 s).
- Therefore no local provider node was created: adding dead localhost endpoints would not create a LIVE route and would violate the required HTTP-200 inference verification. The corresponding six ledger entries will be reclassified with this concrete `local_runtime_not_listening` evidence.
- Next: use the existing browser/session automation only for the specifically session/account-blocked catalog entries, then complete final inference verification.

### [step 18] Six failed direct provider routes demoted through the supported REST API
- `python scripts/automation/fleet_demote_unverified.py` completed after management recovery. It issued six `PUT` disable operations, all HTTP 200, for the standard-chat-proven failures: `amazon-q`, `clinepass`, `lmarena`, `nara`, `openrouter`, and `zai-web`.
- The action followed the required one repair/retest cycle and was restricted to routes with failed standard-chat evidence in `state/fleet_inference_repair.json`; `state/fleet_demotions.json` stores only provider labels and HTTP status.
- Next: session refresh attempt for the documented auth/session blockers, then a fresh all-active/cascade standard-chat sweep.

### [step 19] Browser fallback is unsafe/inapplicable for the three documented blockers
- Inspected the existing generic browser engine without opening browser state. Its fallback maps unknown slugs to `https://<slug>.com` and writes raw page HTML/screenshots, so it cannot safely target `duckduckgo-web`, `hackclub`, or `pollinations` and could persist authentication material.
- It was deliberately not executed: it would not be an honest session-refresh attempt and would violate the no-secret-artifacts rule. The native OAuth refresh script is the safe existing refresh mechanism and will be run instead; the three current blockers remain documented as no session / HTTP 401 auth required.
- Next: run one redacted native OAuth refresh pass and retain any still-expired session as an explicit authentication wall.

### [step 20] Native session/OAuth refresh attempted with a truthful partial result
- `python scripts/automation/oauth_keepalive.py --once` completed: 7 of 9 active OAuth connections refreshed successfully; GitHub and KiloCode failed with `Token refresh failed — provider returned no new token`.
- This was the safe refresh machinery available for configured OAuth connections. It cannot create the absent DuckDuckGo VQD browser session or the upstream API credentials required by HackClub/Pollinations; those three remain `BLOCKED_NO_SESSION` / `BLOCKED_AUTH_REQUIRED` with their existing HTTP evidence.
- Next: acquire a post-demotion full REST snapshot without reactivation, then run a fresh standard chat-completion sweep of every currently active, valid direct owner plus all ten cascade routes.

### [step 21] Fresh full standard-chat sweep verified 28 of 29 current active/cascade routes
- Post-demotion REST snapshot: 56 connections, 22 active / 34 inactive, 25 native-valid tests. `fleet_inference_audit.py` then executed 29 valid `max_tokens=16` standard chat completions: **28 HTTP 200 OpenAI-compatible results** and one failure.
- All 19 current active direct owners returned HTTP 200. Nine cascade routes returned HTTP 200; only `auto/claude-sonnet` timed out at 60,012 ms. The audit intentionally exited 2 (`total=29 valid=28 failed=1`), which is recorded as a real route failure, not a pass.
- Next: inspect the affected combo using the REST-safe combo audit, make at most one evidence-based repair/retest, and otherwise demote/reclassify the failed cascade honestly.

### [step 22] Cascade retry recovered the sole timeout; all current routes are now proven
- REST combo audit confirmed 13 configured combos and no configurable `auto/claude-sonnet` row, so no blind combo edit was made. The transient Anthropic cascade alias was retried once with the same valid chat payload.
- Retry result: `auto/claude-sonnet` returned HTTP 200 with an OpenAI-compatible response in 24,301 ms (`state/fleet_anthropic_retry.json`). Together with the previous sweep, all **19 direct active owners** and all **10 cascade routes** now have current HTTP-200 inference evidence (29/29).
- Next: regenerate the execution ledger from redacted REST/inference evidence and refresh the downstream model forest from the live `/v1/models` catalog.

### [step 23] Reverification found one additional GitHub regression; ledger and forest refreshed
- Targeted recheck of the two active owners omitted by the valid-native-test filter: AI Native returned HTTP 200, while GitHub failed three standard-chat candidates (HTTP 401, 429, and 404) after its native OAuth refresh had already returned no token. GitHub was disabled through one REST `PUT` (HTTP 200); no credential was guessed.
- Added narrowly scoped support for this evidence in the redacted inference/demotion helpers, then regenerated `state/all_296_providers_execution_ledger.json` and `state/omniroute_model_forest.json`. Current ledger: **20 LIVE_ACTIVE**, **10 CASCADE_ROUTED**, **0 CONFIGURED_INACTIVE**, 7 direct routes `BLOCKED_INFERENCE_FAILED`, and 7 local-runtime blocks.
- `state/fleet_live_verified_routes.json` records exactly **30** valid standard-chat routes (20 direct + 10 cascades); downstream forest now has 1,911 currently catalogued models from verified live owners. Next: run the T1–T20 acceptance suite and record its actual result.

### [step 24] Certification run completed with one honest performance failure
- `python acceptance_tests.py` exited 0 but reported `MONETIZER_DEGRADED`: 19/20 checks passed. T1–T12 and T14–T20 all passed, including all route, auth, model, provider-latency, coverage, NVIDIA, free-combo, and VS Code checks.
- The sole failure was T13: root latency measured 336.1 ms against the required <200 ms threshold. This is not marked as fixed; the service was already showing intermittent management/catalog stalls before route work, so a shallow warm-path remeasurement is required before attributing or attempting a repair.
- Next: measure the root endpoint with the same median-of-three approach, then rerun certification only if evidence shows the latency recovered.

### [step 25] Root latency remains above threshold during a saturated CPU interval
- A read-only median-of-three root probe returned 183.4 ms, 283.8 ms, and 215.9 ms (median **215.9 ms**), still above the T13 target. The OmniRoute Node process remains at ~1.71 GB working set while total host CPU sampled at 100%.
- No restart or cache/DB mutation was attempted: the current evidence is a runtime saturation interval, and repository policy requires a sandbox-backed diagnosis/backup before production-level intervention. The model and protected provider endpoints remain responsive.
- Next: allow the observable saturation interval to settle and perform one final read-only median probe; certification will be rerun only if that evidence meets T13.

### [step 26] Read-only telemetry excludes a simple cache failure but confirms runtime load
- Authenticated read-only management telemetry succeeded. Cache statistics are empty (0 entries/hits/misses); telemetry reports 77 active/sticky sessions and recent request latency p50 2,435 ms / p95 19,958 ms, while resilience has a 350 ms minimum request interval and concurrency 6.
- This confirms a server-runtime/queue-load condition, not a provider key issue or cache-corruption finding. It does not prove a safe cache/resilience mutation; no setting, session, database, process, or service lifecycle was changed.
- Next: retain the truthful 19/20 certification result and close the fleet run as blocked only on T13 performance, with all provider-route work and state artifacts complete.

### [step 27] Fleet run final summary — provider objective complete; certification performance block remains
- **Routes gained/revived:** six valid disabled connections were restored earlier in the run; final current standard-chat evidence contains 20 direct + 10 cascade HTTP-200 routes. **Routes lost/demoted:** `amazon-q`, `clinepass`, `github`, `lmarena`, `nara`, `openrouter`, and `zai-web` failed valid inference/repair evidence and were disabled via REST only.
- **Reclassified:** `CONFIGURED_INACTIVE` reduced 16 → **0**. Six local/public candidates became `BLOCKED_LOCAL_RUNTIME` because no advertised localhost endpoint was listening; session/auth walls are retained with exact redacted diagnosis. Ledger and 1,911-model downstream forest were regenerated; 30 exact proven routes are in `state/fleet_live_verified_routes.json`.
- **Verification:** `acceptance_tests.py` = 19/20 PASS; only T13 failed (root latency 336.1 ms, subsequent median 215.9 ms then 913.9 ms under 100% CPU). `git diff --check` passed and a targeted secret-pattern scan found no key/token patterns in files written this run. Status: **MONETIZER_BLOCKED** solely by the unresolved T13 runtime-performance threshold.
