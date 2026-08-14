# AGENTS.md — OmniRoute Phase A

## Mission

This repository is **Phase A: OmniRoute only**.

The final deliverable is a **fully configured, independently operational OmniRoute**.
Neon Architect is NOT an implementation target in this phase.

Do not redesign or optimize Neon. Use the single Neon reference file only when
necessary to understand an existing OmniRoute interface or extraction boundary.

## Phase A completion definition

OmniRoute is complete only when it can independently:

- discover and normalize provider/model information;
- represent providers, accounts, credentials, and models distinctly;
- configure supported providers through the correct API/UI/OAuth/manual paths;
- verify credentials and live connectivity;
- verify representative model inference where appropriate;
- classify provider/model state and failures;
- persist dead/unavailable model state;
- avoid duplicate provider/account/model registrations;
- route by capability and priority;
- fail over without retry storms;
- maintain health/latency/quota-aware state;
- expose a clean machine-readable verified routing pool;
- pass unit/integration/smoke tests.

## Core rule

Models.dev is a **discovery/intelligence source**, not proof of live availability.

A model/provider must not be marked VERIFIED_FREE merely because:
- Models.dev reports cost=0;
- the model name ends with :free;
- an aggregator lists the model;
- a model appears in /models.

## Provider onboarding

Prefer the existing two-stage design:

1. management/API inspection and verification;
2. Playwright/browser interaction only where UI/OAuth/manual action is actually needed.

The latest automation already follows this philosophy. Reuse it rather than
starting over.

Human-in-the-loop is allowed for:
- login;
- MFA;
- CAPTCHA;
- consent/terms;
- provider-specific manual credential generation.

Never attempt to bypass security controls.

## Credential rules

- Never hard-code API keys/passwords into source.
- Never commit cookies/session files/secrets.
- Use environment variables or secure runtime prompts.
- Redact credentials from logs and result files.
- Treat OAuth tokens separately from API keys.

## Account identity

Provider, account, credential, and model are different identities.

Multiple models using the same account/credential must share the same quota and
health bucket.

Multiple OmniRoute aliases pointing to the same underlying local gateway must
not be counted as independent quota accounts.

## Error classification

401/403:
authentication/authorization

404/410:
unavailable route/model unless provider semantics indicate transient behavior

429:
rate limit/quota

408/timeouts:
transient network/provider health

5xx:
transient provider failure

successful real inference:
usable route verification

Do not convert one class into another.

## OpenRouter

OpenRouter is optional.

Do not assume openrouter/free is usable merely because the catalog exposes it.
Account policy/guardrail eligibility can make free routes unavailable.

A policy/eligibility 404 must be recorded as policy/account state and must not
cause repeated retry loops.

## Dead model handling

Persist known permanent failures and suppress repeated discovery/probing until
the configured revalidation window.

Do not hammer models that already proved unavailable.

## Performance

Do not run thousands of live model calls unnecessarily.

Use:

metadata filtering
→ provider/account verification
→ candidate reduction
→ representative model verification
→ capability verification
→ routing-pool promotion.

Cache safe discovery state.

## Source-of-truth hierarchy

1. current OmniRoute runtime behavior
2. latest provider automation and diagnostic evidence
3. current Models.dev registry under registry/
4. historical/reference files
5. old scripts are not authoritative

## Files in this project

automation/
  Current provider handoff/recovery/diagnostic tooling.

registry/
  Models.dev registry copied from the user's local model-intelligence directory.

results/
  Existing observed provider verification evidence.

reference/
  Latest Neon implementation only as an extraction reference.

## Scope discipline

Do not:
- redesign Neon;
- reconcile multiple historical Neon implementations;
- add unrelated UI features;
- perform broad cosmetic refactors;
- spend budget on speculative abstractions.

Do:
- finish OmniRoute as a standalone system;
- preserve working behavior;
- make evidence-backed changes;
- test every substantive change.

## Required workflow

First:
perform a forensic audit and produce an implementation plan.

Second:
inspect current automation and identify missing provider-onboarding capabilities.

Third:
implement the smallest production-safe architecture that satisfies the Phase A
completion definition.

Fourth:
run tests.

Fifth:
run live smoke tests for credentials that are actually available.

Sixth:
produce:

OMNIROUTE COMPLETE

with:
- active runtime/source files
- provider count
- configured accounts
- verified providers
- verified models/routes
- free routes
- auth-required routes
- unavailable/restricted routes
- remaining blockers
- tests run/results
- recommended next steps

## Budget control

Do not enter an open-ended refactor.

Once Phase A acceptance criteria are satisfied and tests pass, STOP.

Do not begin Neon work.
