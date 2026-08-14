# Implementation Plan — OmniRoute Monetizer V1

## Overview

This document defines the ordered, idempotent implementation sequence for
bringing the OmniRoute environment from "already running" to **MONETIZER_READY**
or **MONETIZER_BLOCKED**. Every phase must preserve the live runtime and
converge on repeated execution.

---

## Phase 0 — Runtime Preflight

**Goal:** Confirm OmniRoute is reachable; abort or defer if not.

1. `GET http://localhost:20128/v1/models` (or equivalent health endpoint).
2. If unreachable → record in `DEFERRED_ACTIONS.md`, exit **MONETIZER_BLOCKED**.
3. If reachable → log timestamp, latency baseline, and proceed.

> **CRITICAL:** Never stop, restart, kill, rebind, or replace the running
> OmniRoute service on port 20128. If any phase determines a restart is
> required, defer it and continue safe work.

---

## Phase 1 — Secure Management Authentication

**Goal:** Obtain a management session token without hard-coded secrets.

1. Read management password from environment variable
   (`OMNIRoute_ADMIN_PASSWORD` or equivalent).
2. Authenticate:
   ```
   POST http://localhost:20128/api/auth/login
   Content-Type: application/json

   {"password": "<from env>"}
   ```
3. Store the returned `auth_token` cookie for subsequent `/api/*` calls.
4. If the env var is missing → prompt the user or read from a secure vault;
   **never** fall back to a hard-coded default.
5. Verify the token works: `GET /api/providers` should return 200.

**Security rules:**
- No secrets in source code, logs, screenshots, or git history.
- Tokens live in memory for the session duration only.
- All credential material sourced exclusively from environment variables.

---

## Phase 2 — Provider / Account / Credential / Model / Route Normalization

**Goal:** Ensure all entities maintain distinct identities and no data is lost.

1. Fetch current state: `GET /api/providers` → `{connections: [...]}`.
2. For each connection, record:
   - **Provider ID** (unique, stable)
   - **Account identity** (user/org, if applicable)
   - **Credential type** (API key, OAuth, no-auth) and source reference
   - **Model list** (upstream model IDs)
   - **Route aliases** (if any mapping exists)
3. Normalize:
   - Deduplicate providers sharing the same upstream base URL but different IDs.
   - Tag providers with source-of-truth tier (see §11).
   - Preserve all healthy connections untouched.
4. Produce a normalization report with before/after counts.

**Idempotency:** Second run must detect existing normalized state and skip.

---

## Phase 3 — API-First Provider Onboarding & Repair

**Goal:** Bring non-functional providers into working state using the management
API, falling back to Playwright only when the API cannot resolve the issue.

### 3.1 — Connection Testing

For each provider with a non-healthy status:

```
POST /api/providers/{id}/test
```

Response shape:
```json
{
  "valid": true | false,
  "diagnosis": {
    "status": "ok" | "auth_error" | "unavailable" | "quota" | "timeout",
    "detail": "..."
  }
}
```

### 3.2 — Automated Repair (API-level)

| Diagnosis | Action |
|---|---|
| `auth_error` (401/403) | Attempt `POST /api/providers/{id}/refresh` (OAuth refresh). If refresh fails → mark for UI reauth handoff. |
| `unavailable` (404/410) | Mark DEAD. No API repair possible. |
| `quota` (429) | Mark COOLDOWN with backoff window. |
| `timeout` (408/5xx) | Retry up to 2× with exponential backoff, then mark COOLDOWN. |

### 3.3 — Playwright Handoff

When API-level repair fails for an auth_error:
1. Generate a Playwright script targeting the provider's OAuth login page.
2. Record the handoff point and expected post-condition.
3. The script must **not** log or persist credentials.

### 3.4 — No-Auth Providers

For providers requiring no authentication:
1. Verify the base URL is reachable.
2. Register the provider if not already present.
3. Proceed to verification.

---

## Phase 4 — Minimal Live Verification

**Goal:** Confirm each candidate route with exactly one representative inference.

1. For each provider passing Phase 3, send a single minimal chat completion:
   ```
   POST http://localhost:20128/v1/chat/completions
   {
     "model": "<concrete-model-id>",
     "messages": [{"role": "user", "content": "ping"}],
     "max_tokens": 5
   }
   ```
2. Success (200 + valid response body) → promote to **VERIFIED**.
3. Failure → classify error (see `STATE_MACHINE.md`) and update state.
4. **No mass probing.** One inference per candidate model is sufficient.

> **Promotion rule:** A concrete route enters VERIFIED **only** after
> successful live inference. Registry metadata alone is never sufficient.

---

## Phase 5 — Routing Pools

**Goal:** Assemble verified models into the canonical routing pools.

### Pool Definitions

| Pool | Alias | Composition | Fallback |
|---|---|---|---|
| **Frontier** | `frontier` | Frontier-tier models only | None — no lower-tier fallback |
| **Pro Coding** | `auto/pro-coding` | Verified coding-optimized models | — |
| **Pro Reasoning** | `auto/pro-reasoning` | Verified reasoning-optimized models | — |
| **Pro Chat** | `auto/pro-chat` | Verified general chat models | — |
| **Legacy aliases** | `best`, `fast`, `free` | Preserve only verified-working entries | — |

### Rules

- Frontier pool contains **only** Frontier-class providers. No silent downgrade.
- Zed sends model ID `frontier` (not `auto/frontier`) for the Frontier entry.
- `free` alias: include only models with **evidence** of free entitlement.
  Never claim FREE from registry metadata alone.
- Each pool entry references a VERIFIED concrete model.
- Pools are serialized as JSON and validated before deployment.

---

## Phase 6 — Client Integration

### 6.1 — Zed

- Base URL: `http://localhost:20128/v1`
- API key: from env var (or placeholder if OmniRoute requires none)
- Model list populated from routing pools
- Frontier entry uses model ID `frontier`
- Preserve unrelated Zed settings

### 6.2 — Codex

- Base URL: `http://localhost:20128/v1`
- Model aliases mapped to OmniRoute routing pools
- Verify a completion round-trip

### 6.3 — Claude Code

- Base URL: `http://localhost:20128/v1`
- Preserve existing Claude Code configuration for non-OmniRoute providers
- Verify a completion round-trip

---

## Phase 7 — Performance Engineering

**Goal:** Baseline and improve end-to-end latency without degrading routing quality.

### 7.1 — Baseline Measurements

| Metric | Method |
|---|---|
| `/v1/models` latency | Timed GET |
| Chat completion latency | Timed POST, representative model |
| Streaming TTFT | First-chunk timing on streaming request |
| Routing selection latency | Internal measurement or timing delta |
| Retry/timeout rate | Count retries across verification runs |
| Concurrency behavior | Parallel request test (4–8 concurrent) |
| Memory/CPU | OS-level snapshot during load |
| Storage/DB latency | Query timing for provider/model lookups |

### 7.2 — Optimization Priorities (non-disruptive only)

1. **Caching** — model list, provider capabilities
2. **Deduplication** — eliminate redundant discovery/provider work
3. **Connection reuse** — HTTP keep-alive, connection pooling
4. **Candidate reduction** — prune DEAD/COOLDOWN routes early
5. **Bounded retries** — cap retry count, use exponential backoff
6. **Dead-route suppression** — skip known-DEAD providers without probing
7. **Reduced discovery repetition** — cache registry lookups

> Never trade routing quality for superficial latency improvements.
> Any optimization requiring a service restart → `DEFERRED_ACTIONS.md`.

---

## Phase 8 — Acceptance Tests

Run after all phases. Every test must pass for **MONETIZER_READY**.

| # | Test | Pass Criteria |
|---|---|---|
| 1 | OmniRoute reachable | `GET /v1/models` returns 200 |
| 2 | Management auth works | `POST /api/auth/login` returns valid token |
| 3 | Provider count stable | Count matches expected (verified + dead) |
| 4 | Frontier pool non-empty | ≥ 1 VERIFIED Frontier model |
| 5 | Pro pools populated | Each pro pool has ≥ 1 VERIFIED model (or documented gap) |
| 6 | Frontier inference | Completion with `model: frontier` succeeds |
| 7 | Pro coding inference | Completion with a pro-coding model succeeds |
| 8 | Pro reasoning inference | Completion with a pro-reasoning model succeeds |
| 9 | Pro chat inference | Completion with a pro-chat model succeeds |
| 10 | Zed integration | Zed can list models and complete via OmniRoute |
| 11 | Codex integration | Codex completion round-trip succeeds |
| 12 | Claude Code integration | Claude Code completion round-trip succeeds |
| 13 | No leaked secrets | Logs, reports, and source contain no credentials |
| 14 | Idempotency | Second run converges — no resources destroyed/recreated |
| 15 | Performance baseline | Latency metrics recorded; no regressions from prior run |

Final output: sanitized report + **MONETIZER_READY** or **MONETIZER_BLOCKED**
with deferred actions listed.

---

## §A — Cross-Cutting Principles

### Idempotency

- Never blindly destroy/recreate a resource.
- Inspect first; update only when demonstrably stale or broken.
- Second run should converge toward "already configured / verified."

### Promotion Rule

A concrete route enters VERIFIED **only** after successful live inference
or other trustworthy current verification. Registry metadata, historical
records, or provider claims are insufficient alone.

### Source of Truth (ordered)

1. **Live OmniRoute behavior** — what the running service reports right now
2. **Phase-A evidence** — latest automation results and logs
3. **Registry discovery data** — provider/model catalog information
4. **Historical/reference material** — old scripts, notes, prior configs

Old scripts are **not** authoritative. When in conflict, live behavior wins.

### Safety

- No hard-coded secrets anywhere in source, config, or logs.
- No mass model probing — minimal representative tests only.
- No Neon database interaction.
- No rebuilding healthy routing.
- All credentials sourced from environment variables.
