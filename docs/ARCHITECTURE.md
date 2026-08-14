# OmniRoute Monetizer V1 — Architecture

## Mission
One reproducible, idempotent Windows bootstrap that takes the current OmniRoute
environment from "already running / partially configured" to a monetizer-ready
client environment.

## CRITICAL LIVE-RUNTIME RULE
The running OmniRoute service on port 20128 is immutable during agent execution.

NEVER:
- stop/restart/remove/reinstall the OmniRoute service
- kill its Node process
- change its service name or port
- replace its live launcher
- perform an operation that severs the agent's own OmniRoute API path

You may inspect it and use supported management APIs. If a restart appears
necessary, defer it and report it.

## Architecture
0. Safety/preflight
   -> confirm OmniRoute reachable
   -> create backups/logs
1. Runtime discovery
2. Secure management authentication
3. Provider/account/credential/model/route normalization
4. API-first provider onboarding/repair
   -> targeted Playwright/manual handoff only when required
5. Verification
   -> connection test
   -> representative concrete inference
6. Routing pools
   - frontier (Frontier-only; no lower-tier fallback)
   - auto/pro-coding
   - auto/pro-reasoning
   - auto/pro-chat
   - preserve other working best/fast/free aliases
7. Client integration
   - Zed
   - Codex
   - Claude Code
8. Acceptance tests
9. Sanitized final report

## Idempotency
If a resource already exists:
- inspect it
- preserve it
- update only when demonstrably stale/broken
- never blindly destroy/recreate it

Second run should converge toward "already configured / verified".

## Source of truth
1. live OmniRoute behavior
2. latest Phase-A automation/evidence
3. registry discovery data
4. historical/reference material
5. old scripts are not authoritative

## Promotion rule
A concrete route enters the verified pool only after successful live inference
or other trustworthy current verification.

## Security
Never hard-code or print passwords, API keys, OAuth tokens, cookies, or secrets.
Never copy runtime secrets/databases into the project.

## Failure classes
401/403 auth; 404/410 unavailable/policy unless proven transient; 429 quota;
timeout/408 transient health; 5xx transient upstream.

## Deliverables
- master monetizer script
- sanitized logs
- verified routing-pool JSON
- client configuration status
- deferred actions report
- MONETIZER_READY or MONETIZER_BLOCKED

## Performance Engineering

Performance is a required Monetizer objective.

Baseline before substantive optimization:
- /v1/models latency
- representative /v1/chat/completions latency
- time-to-first-token for streaming when practical
- routing-selection latency
- retry count / timeout rate
- provider-selection latency
- memory / CPU behavior
- storage/database latency
- client-side request overhead

Prioritize non-disruptive improvements:
- caching
- candidate reduction
- deduplication
- connection reuse
- bounded retries
- dead-route suppression
- reduced discovery repetition
- efficient serialization/database access

Never lower routing quality simply to hide latency.

If an optimization requires an OmniRoute service restart, DO NOT perform it.
Record it in DEFERRED_ACTIONS.md instead.
