# AGENTS.md — OmniRoute Monetizer

## Mission
Build and maintain the master end-to-end OmniRoute Monetizer.

## CRITICAL SAFETY RULE
OMNIROUTE IS A LIVE DEPENDENCY OF THE AGENT.

NEVER stop, restart, remove, reinstall, kill, rebind, or replace the running
OmniRoute service/process on port 20128.

You may inspect it and use supported /api management calls.

If a change requires a restart:
1. Do not execute it.
2. Record it in DEFERRED_ACTIONS.md.
3. Continue all safe work.
4. Report the deferred action.

## Freedom to improve
You may consolidate scripts, repair stale logic, add tests, improve provider
onboarding/verification, implement dead-route state, and improve Zed/Codex/
Claude integration.

Do not preserve bad code merely because it exists.

## Required workflow
1. Read project docs/evidence.
2. Inspect live state.
3. Plan.
4. Make bounded changes.
5. Test substantive changes.
6. Preserve working state.
7. Produce acceptance report.

## Do not
- hard-code secrets
- expose credentials
- mass-probe models
- treat registry metadata as live verification
- call a route FREE without evidence
- touch Neon
- rebuild healthy routing unnecessarily

## Completion
End with MONETIZER_READY or MONETIZER_BLOCKED.

## PERFORMANCE ENGINEERING — REQUIRED

Performance is part of the Monetizer acceptance target.

Baseline and investigate:
- /v1/models latency
- chat completion latency
- streaming TTFT where practical
- routing/provider selection latency
- retry/timeout amplification
- concurrency/queueing
- memory/CPU
- storage/database latency
- duplicate discovery/provider/model work

Prefer caching, deduplication, connection reuse, candidate reduction, bounded
retries, dead-route suppression, and other non-disruptive changes.

Do not trade routing quality for superficial latency improvements.

CRITICAL:
Never stop, restart, remove, reinstall, kill, or rebind the running OmniRoute
service. Any restart-dependent improvement must be deferred and recorded.

## BROWSER / DOM AUTOMATION — REQUIRED

The Monetizer must reuse the Phase-A browser evidence and provide a generalized
browser/DOM automation layer.

Required flow:
API inspection/repair first
→ targeted Playwright discovery
→ safe provider UI actions
→ human handoff when MFA/CAPTCHA/consent/manual credential generation is needed
→ re-test via OmniRoute management API
→ persist sanitized result.

The browser engine must:
- never stop/restart/kill/rebind OmniRoute;
- never bypass MFA/CAPTCHA/consent;
- never log input values, cookies, tokens, passwords, API keys or auth headers;
- avoid secret-bearing screenshots/artifacts where feasible;
- support provider-specific adapters on top of a generic DOM discovery layer.

A provider may only be promoted after live API/inference verification.
