# OmniRoute Phase A — Engineering Handover

## 1. PHASE A OBJECTIVE

**VERIFIED — `AGENTS.md`:** Phase A is an independently operational OmniRoute that can discover and normalize provider/model data; keep provider, account, credential, and model identities distinct; configure providers through supported API/UI/OAuth/manual paths; verify credentials and representative inference; classify and persist failures/dead models; route by capability and priority; fail over without retry storms; maintain health/latency/quota-aware state; expose a machine-readable verified routing pool; and pass unit/integration/smoke tests.

**VERIFIED:** Models.dev data, zero cost metadata, `:free` names, aggregator listings, and `/models` presence do **not** prove a route is live, free, authorized, or verified.

## 2. VERIFIED RUNTIME

- **VERIFIED:** External OmniRoute dashboard/runtime was targeted at `http://localhost:20128`; `/api/*` is management and `/v1/*` is the OpenAI-compatible inference surface. Sources: `automation/omniroute_ui_diagnostic_v10.py`, `automation/omniroute_provider_recovery_v11_smoketested.py`.
- **VERIFIED:** Recovery script commentary identifies an observed OmniRoute **v3.8.49** UI/API bundle.
- **UNVERIFIED:** Node runtime/version, installation location, service/NSSM structure, live data directory, process launcher, database engine, and service persistence are not present in this workspace or prior audit evidence.

## 3. VERIFIED ARCHITECTURE

- **VERIFIED:** Management login: `POST /api/auth/login`; provider inventory: `GET /api/providers`; connection validation: `POST /api/providers/{id}/test`; OAuth refresh: `POST /api/providers/{id}/refresh`.
- **VERIFIED:** `/api/providers` is expected to return a `connections` collection. Automation uses connection `id` for test/refresh and reads `provider`, `authType`, `email`, and/or `name` where present.
- **VERIFIED:** `/v1/chat/completions` and `/v1/models` are used as inference/model-facing paths by `enable_omniroute_noauth.py`.
- **INFERENCE:** The runtime has a dashboard-backed persistent provider-connection store, because connections have stable IDs and are managed/tested via API. Its schema and storage are unverified.
- **UNVERIFIED:** Runtime components, API implementation, persistent-state format/location, model import/sync implementation, route persistence, health/quota state, and routing algorithm are not supplied in this project.

## 4. AUTHENTICATION

- **VERIFIED:** Management API authentication uses `POST /api/auth/login`; scripts obtain credentials through runtime input/environment handling. `OMNIROUTE_BASE_URL` may include `/v1`, which scripts strip for management operations.
- **VERIFIED:** `enable_omniroute_noauth.py` accepts a management key via `--key`; this is a security risk because command-line secrets can leak to history/process listings.
- **VERIFIED:** OAuth connections are represented by `authType: "oauth"`; recovery tries API refresh then targeted visible-browser reauthentication/import.
- **VERIFIED:** Manual handoff is required/allowed for login, MFA, CAPTCHA, consent, account selection, manual key generation/import, Save, and Test.
- **UNVERIFIED:** Credential storage, encryption, token lifecycle, OAuth callback details, account identity extraction, and secret-store integration.

## 5. PROVIDER MANAGEMENT

### Actually discovered

- **VERIFIED:** `POST /api/auth/login`
- **VERIFIED:** `GET /api/providers`
- **VERIFIED:** `POST /api/providers/{connection-id}/test`
- **VERIFIED:** `POST /api/providers/{connection-id}/refresh`
- **UNVERIFIED / compatibility probes only:** `POST /api/providers`, `/api/provider-nodes`, `/api/providers/list`, and update/enable variants are tried by `enable_omniroute_noauth.py`; this is not a confirmed stable management contract.

### Automation boundary

- **VERIFIED:** Inventory, connection testing, OAuth refresh, evidence capture, navigation, and bounded targeted UI reauth are automatable by current tools.
- **VERIFIED:** Human actions remain required for login/MFA/CAPTCHA/consent/account choice/manual credential generation.
- **UNVERIFIED:** Safe fully automated onboarding for any specific provider; no complete provider-by-provider onboarding matrix exists.

## 6. MODEL / REGISTRY

- **VERIFIED:** `registry/api.json` has 184 provider records with provider IDs, environment-variable metadata, package/docs metadata, optional API metadata, and provider-specific model mappings.
- **VERIFIED:** `registry/models.json` has 310 canonical model records with IDs, capabilities (for example modalities, reasoning/tool-call flags), limits, and model metadata.
- **VERIFIED:** `registry/catalog.json` contains the same 184 provider IDs and 310 canonical model IDs, grouped under `providers` and `models`.
- **VERIFIED:** Provider-specific mapping counts can exceed canonical model count (e.g. OpenRouter 348 mappings); provider/route alias and canonical model must remain distinct identities.
- **VERIFIED:** Registry and CSV candidate lists are discovery/intelligence artifacts only. They do not establish account authorization, upstream availability, cost entitlement, live inference, or verified routing-pool membership.

## 7. EXISTING AUTOMATION

| File | Safe use | Must not be treated as |
|---|---|---|
| `automation/omniroute_manual_provider_handoff_v12.py` | Opens a provider dashboard page in visible Playwright and stops for an operator. Does not click controls or mutate provider API state. | Automated onboarding or verification. |
| `automation/omniroute_provider_recovery_v11_smoketested.py` | Tests existing connections; for selected failed OAuth connections tries refresh, then exact UI reauth/import, and finally re-tests. API `valid=true` is its success criterion. | Catalog/model optimizer, persistent health system, or production retry policy. |
| `automation/omniroute_ui_diagnostic_v10.py` | Non-mutating provider diagnostic: API inventory/tests plus screenshots/DOM/API evidence. | Completely passive collection: it calls `/test` for every connection. |
| `automation/enable_omniroute_noauth.py` | Experimental management API/provider-enable helper with optional generic `auto*` probes. | Proof that candidates are no-auth, free, configured, or inference-verified. |
| `automation/run_*.ps1` | Validate/bootstrap Python/Playwright and invoke the matching tools. | Reproducible standalone OmniRoute deployment. |

**VERIFIED security note:** v10 applies JSON key-name redaction, but screenshots/page text may still capture secrets; v11 writes JSON without the v10 redaction helper. Harden evidence handling before operational reuse.

## 8. VERIFIED LIVE EVIDENCE

- **VERIFIED — historical result file:** `results/final_connection_status.json` reports 69 connection tests: 18 API-test valid and 51 failed. The 18 historical valid providers are: `agy`, `ainative`, `amazon-q`, `antigravity`, `api-airforce`, `bazaarlink`, `blackbox`, `brave-search`, `codex`, `friendliai`, `kilocode`, `kimi-coding`, `novita`, `nvidia`, `opencode`, `openrouter`, `sambanova`, `xai`.
- **VERIFIED:** This is connection-level `/test` evidence only, not proof of current validity, a concrete model inference, free access, fallback, or verified-pool membership.
- **VERIFIED:** Failure summary: 38 invalid-key upstream auth failures; 4 unsupported provider tests; 4 invalid outbound URL/upstream-unavailable failures; 2 missing-base-URL failures; plus missing AWS credentials and two detailed OAuth/runtime failures.
- **VERIFIED:** Detailed `xai-oauth` evidence (2026-08-12) returned management HTTP 200 containing `valid:false` and upstream status **402** after refresh; it remained unavailable.
- **VERIFIED:** Detailed `cline` evidence (2026-08-12) returned management HTTP 200 containing `valid:false`; diagnosis was local CLI runtime not installed; refresh did not resolve it.
- **UNVERIFIED:** No observed 401/403 or 404/410 response payload/status is preserved in the audited results. `AGENTS.md` defines their intended classifications but this is policy, not observed runtime evidence.
- **UNVERIFIED:** No OpenRouter privacy/policy finding is contained in the audited files. `AGENTS.md` only warns that OpenRouter free catalog routes may be unavailable due to account policy/guardrail eligibility and that policy/eligibility 404 must be persisted/suppressed.
- **VERIFIED:** No concrete successful provider/account/model inference result was found in project evidence.

## 9. CURRENT GAPS

### Known blockers

- **VERIFIED:** No standalone OmniRoute runtime source/distribution, deployment manifest, configuration template, dependency lock, state schema/store, test suite, or version-control repository is present.
- **VERIFIED:** `INITIAL_PROMPT.txt`, required by the initial audit instruction, is absent.
- **VERIFIED:** No durable verified routing-pool artifact/API or model-route inference evidence exists here.

### Unknowns

- **UNVERIFIED:** Actual installed runtime/service location, Node/NSSM details, data directory, database, credential encryption, supported management mutation contract, provider onboarding requirements, and live account/credential availability.

### Work required

- **INFERENCE:** Obtain/pin the runtime or explicitly authorize a new standalone runtime; implement/verify identity, persistence, bounded verification, health/quota/dead-route state, routing/fallback, secure operations, routing-pool output, and layered tests.

## 10. IMPLEMENTATION ORDER

1. Read `AGENTS.md` and this handover; keep Neon out of scope.
2. Obtain the actual OmniRoute runtime/source/distribution and exact deployment/API contract; do not infer it from helper scripts.
3. Restore/provide missing `INITIAL_PROMPT.txt` if it carries additional requirements.
4. Capture sanitized fixtures/contracts for the verified management and inference endpoints.
5. Establish reproducible deployment, configuration, secure credential handling, and persistent state.
6. Import registry data as discovery metadata only; model/provider/route/account/credential identities must be distinct.
7. Harden automation: remove CLI secret exposure; redact recovery output; prevent secret-bearing screenshots/DOM artifacts; pin bootstrap dependencies.
8. Build a provider onboarding matrix and bounded connection + representative concrete-route verification pipeline.
9. Persist classifications, cooldown/dead-route state, account quota/health, retry budgets, and failure evidence.
10. Publish a machine-readable verified routing pool containing only successful concrete routes.
11. Run unit/integration tests; then perform minimal authorized live smoke tests with human handoff as required.
12. Declare Phase A complete only when the acceptance criteria below are objectively met.

## 11. FILE MAP

### Read first

1. `D:\omniroute-phase-a\AGENTS.md`
2. `D:\omniroute-phase-a\CODEX_HANDOFF.md`
3. `D:\omniroute-phase-a\docs\EXCLUDED_FILES.txt`

### Read second

4. `D:\omniroute-phase-a\automation\omniroute_ui_diagnostic_v10.py`
5. `D:\omniroute-phase-a\automation\omniroute_provider_recovery_v11_smoketested.py`
6. `D:\omniroute-phase-a\automation\omniroute_manual_provider_handoff_v12.py`
7. `D:\omniroute-phase-a\results\final_connection_status.json`
8. `D:\omniroute-phase-a\results\connection_results.json`

### Read later / discovery reference only

9. `D:\omniroute-phase-a\automation\enable_omniroute_noauth.py`
10. `D:\omniroute-phase-a\automation\run_omniroute_ui_diagnostic_v10.ps1`
11. `D:\omniroute-phase-a\automation\run_omniroute_provider_recovery_v11_updated.ps1`
12. `D:\omniroute-phase-a\automation\run_omniroute_manual_provider_handoff_v12.ps1`
13. `D:\omniroute-phase-a\registry\api.json`
14. `D:\omniroute-phase-a\registry\catalog.json`
15. `D:\omniroute-phase-a\registry\models.json`
16. `D:\omniroute-phase-a\results\free-chat-candidates.csv`, `zero-cost-clean.csv`, `agent-free-shortlist*.csv` — metadata-only candidate lists.

## 12. ACCEPTANCE CRITERIA

**VERIFIED — derived directly from `AGENTS.md`:** Phase A is complete only if OmniRoute independently:

- discovers/normalizes provider-model information and preserves separate provider/account/credential/model identities;
- configures supported providers via correct API/UI/OAuth/manual path with safe credential handling;
- verifies credentials/live connections and representative real inference where appropriate;
- classifies failures correctly, persists unavailable/dead-model state, and avoids duplicate registration/retry storms;
- routes by capability and priority with health/latency/quota-aware fallback;
- exposes a clean machine-readable verified routing pool;
- passes unit, integration, and smoke tests.

**Objective promotion condition:** a route enters the verified pool only after successful real inference for its concrete provider/account/route identity. Metadata alone must never mark it `VERIFIED_FREE`.

## 13. SAFETY RULES

- **VERIFIED:** Never expose credentials, API keys, passwords, OAuth tokens, cookies, or sessions in source, terminal output, logs, result files, screenshots, or commits.
- **VERIFIED:** Never reuse hard-coded credentials in historical material; `docs/EXCLUDED_FILES.txt` identifies excluded legacy scripts with hard-coded secrets.
- **VERIFIED:** Do not copy `.env`, OAuth tokens, SQLite state, or secrets into this project directory.
- **VERIFIED:** Do not directly mutate SQLite unless no supported management interface exists and this is explicitly justified.
- **VERIFIED:** Treat provider, account, credential, model, and aliases to a common gateway as distinct/shared identities as applicable; do not count aliases as independent quota accounts.
- **VERIFIED:** Classify 401/403 as auth, 404/410 as unavailable unless transient semantics are demonstrated, 429 as quota/rate limit, timeout/408 and 5xx as transient; do not collapse these classes.
- **VERIFIED:** Persist permanent/policy failures and use a revalidation window rather than repeatedly probing them.
- **VERIFIED:** Neon remains **OUT OF SCOPE**. Do not inspect, modify, recreate, or add Neon materials/dependencies.
