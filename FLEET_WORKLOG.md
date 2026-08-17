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
