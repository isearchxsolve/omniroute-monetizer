# Provider Policy — OmniRoute Monetizer

## Overview

This document defines the authoritative policy for provider management within
the OmniRoute Monetizer. It governs which providers are trusted, how identities
are separated, how credentials are handled, and how edge cases are resolved.

---

## Historically Verified Providers (OK)

The following 18 providers have been verified as functional through live
evidence (successful inference or valid connection test). They are eligible for
routing pools subject to current re-verification.

| # | Provider ID | Notes |
|---|---|---|
| 1 | `agy` | — |
| 2 | `ainative` | — |
| 3 | `amazon-q` | — |
| 4 | `antigravity` | — |
| 5 | `api-airforce` | — |
| 6 | `bazaarlink` | — |
| 7 | `blackbox` | — |
| 8 | `brave-search` | — |
| 9 | `codex` | — |
| 10 | `friendliai` | — |
| 11 | `kilocode` | — |
| 12 | `kimi-coding` | — |
| 13 | `novita` | — |
| 14 | `nvidia` | — |
| 15 | `opencode` | — |
| 16 | `openrouter` | See OpenRouter policy (§5) |
| 17 | `sambanova` | — |
| 18 | `xai` | — |

> **Status is not permanent.** Each provider must pass live re-verification
> per the state machine (`STATE_MACHINE.md`) on every monetizer run. A
> historically OK provider that fails re-verification transitions to DEAD.

---

## Non-Functional Providers

41 providers have been observed as non-functional. Common failure reasons:

| Failure Reason | Description |
|---|---|
| `upstream_auth_error` | 401/403 from upstream — credentials invalid, expired, or revoked |
| `upstream_unavailable` | 404/410 or connection refused — service gone or endpoint removed |
| `missing_base_url` | Provider has no configured base URL |
| `no_credentials` | Provider requires credentials that are not available |
| `oauth_expired` | OAuth token expired and refresh failed |
| `policy_blocked` | Provider functional but excluded by policy |

### Handling

- Non-functional providers are marked **DEAD** in the state machine.
- They are excluded from all routing pools.
- They are re-evaluated per the DEAD revalidation window (24 hours).
- A non-functional provider is **never** silently removed — it remains
  tracked as DEAD so recovery is possible if the upstream issue resolves.

---

## Identity Separation Rules

Provider, account, credential, model, and route are **distinct identities**.
Conflating them causes bugs, credential leaks, and routing errors.

### Definitions

| Entity | Identity | Example |
|---|---|---|
| **Provider** | The upstream AI service | `openrouter`, `xai`, `nvidia` |
| **Account** | The user/org identity at the provider | User account, API org |
| **Credential** | The authentication material | API key, OAuth token, session cookie |
| **Model** | A specific AI model served by a provider | `gpt-4o`, `claude-sonnet-4-20250514` |
| **Route** | A routing alias that maps to one or more models | `frontier`, `auto/pro-coding` |

### Rules

1. **One provider, one identity.** Never merge two providers that have
   different base URLs or different credential scopes, even if they serve
   the same models.

2. **Credentials belong to accounts, not providers.** If a provider supports
   multiple accounts, each account has its own credential entry.

3. **Models belong to providers.** The same model name at two different
   providers are distinct model entries (e.g., `gpt-4o` at `openrouter`
   vs. `gpt-4o` at `nvidia`).

4. **Routes reference models, not providers.** A route alias points to
   specific verified model(s). The routing layer selects among them.

5. **Never reuse a credential across providers.** Each credential is scoped
   to exactly one provider+account pair.

---

## OAuth Recovery Path

When an OAuth-authenticated provider fails with an auth error (401/403):

### Step 1 — Token Refresh

```
POST /api/providers/{id}/refresh
```

- If the provider supports OAuth refresh and the refresh token is valid,
  OmniRoute attempts to obtain a new access token automatically.
- Success → re-test (`POST /api/providers/{id}/test`). If valid → AUTH_OK.

### Step 2 — UI Reauth Handoff

If refresh fails (refresh token expired or revoked):

1. Generate a Playwright-based browser automation script targeting the
   provider's OAuth login page.
2. The script opens the login flow in a visible browser window.
3. The user completes authentication interactively.
4. The script captures the resulting token/session.
5. The token is passed to OmniRoute via the management API.

**The script must never log, print, or persist credentials to disk.**

### Step 3 — Manual Fallback

If automated reauth fails:

1. Record the failure in the monetizer log.
2. Mark the provider as **DEAD** with reason `oauth_expired`.
3. Add to `DEFERRED_ACTIONS.md` for manual user intervention.
4. Continue with remaining providers — do not block the pipeline.

---

## No-Auth Provider Onboarding

Some providers serve models without authentication (public endpoints).

### Policy

1. **Verify reachability.** `GET` the provider's base URL or models endpoint.
   Must return 200.
2. **Register if absent.** Add via management API if not already in
   `/api/providers`.
3. **Test connection.** `POST /api/providers/{id}/test` → `valid: true`.
4. **Verify inference.** Single minimal `POST /v1/chat/completions` call.
5. **Promote to VERIFIED** only after step 4 succeeds.

### Risks

- No-auth endpoints may have stricter rate limits or less reliability.
- Mark no-auth providers with a `no-auth` tag for routing-pool awareness.
- If a no-auth endpoint returns 429, apply the standard COOLDOWN path.

---

## OpenRouter Policy

OpenRouter (`openrouter`) requires special handling:

### Free Routes

- OpenRouter "free" model routes **may be unavailable** due to OpenRouter's
  own account policy, credit system, or provider-side restrictions.
- A model listed as "free" in the OpenRouter catalog is **not** automatically
  eligible for the `free` routing alias.
- **Evidence of free entitlement** (successful inference without paid credits)
  is required before adding any OpenRouter model to the `free` pool.

### Paid Routes

- OpenRouter paid routes function normally if the account has credits.
- Credential management follows the standard OAuth/API-key path.

### Routing Implications

- OpenRouter models may appear in `frontier`, `auto/pro-*`, or other pools
  if verified through live inference.
- The `free` alias must never include OpenRouter models based on catalog
  metadata alone.

---

## Dead Model Persistence

### Policy

Dead models and providers are **persisted, not deleted.**

1. **Track, don't remove.** A DEAD entity remains in the system with its
   state, failure reason, and timestamp.
2. **Exclude from routing.** DEAD entities are filtered out of all routing
   pool queries.
3. **Revalidate on schedule.** Per `STATE_MACHINE.md`, DEAD entities are
   re-evaluated every 24 hours.
4. **Preserve evidence.** The failure diagnosis (HTTP status, error body
   summary) is retained for debugging and trend analysis.

### Rationale

- Removing dead entities loses diagnostic history.
- Transient upstream outages may resolve — persistence enables automatic
  recovery without re-discovery.
- Routing pool construction queries only VERIFIED entities, so dead entries
  have zero runtime cost.

---

## Credential Security Policy

### Absolute Rules

1. **Environment variables only.** All credentials (API keys, passwords,
   OAuth tokens) are read from environment variables. No exceptions.

2. **Never in source code.** No credential material in any `.py`, `.js`,
   `.json`, `.yaml`, `.toml`, `.md`, or any other file committed to the
   repository.

3. **Never in logs.** Monetizer scripts must redact or omit credentials
   from all log output, including debug logs.

4. **Never in screenshots.** Any captured UI screenshots or terminal output
   must have credential fields masked.

5. **Never in git history.** If a credential is accidentally committed,
   it must be rotated immediately and the history rewritten.

6. **Never fabricated.** If a credential is unavailable, the provider
   transitions to CREDENTIAL_PENDING or DEAD. The system never generates
   fake credentials to satisfy a registration requirement.

### Storage

- Runtime credentials exist only in memory (session-scoped tokens) or in
  OmniRoute's internal credential store (managed by OmniRoute itself).
- The monetizer does not maintain its own credential database.
- All credential operations go through OmniRoute's management API.

### Audit

- Every credential operation (supply, refresh, revoke) is logged with
  provider ID and timestamp — never the credential value.
- The sanitized final report confirms: "No credentials in source, logs,
  or deliverables."

---

## Fabrication and Evidence Rules

| Rule | Detail |
|---|---|
| **Never fabricate credentials** | If a credential is missing, mark CREDENTIAL_PENDING. Do not invent API keys or tokens. |
| **Never claim FREE without evidence** | A model is FREE only after successful inference that did not consume paid credits. Registry metadata is not evidence. |
| **Never trust registry alone** | Registry data is tier-3 in the source-of-truth hierarchy. Live behavior (tier-1) always wins. |
| **Never mass-probe** | Use minimal representative tests (1 inference per model). Do not enumerate all models via repeated calls. |

---

## Summary

This policy ensures that every provider in OmniRoute is:

- **Identified** correctly (distinct provider/account/credential/model/route)
- **Authenticated** securely (env vars only, never hard-coded)
- **Verified** with evidence (live inference, not metadata)
- **Recovered** gracefully (OAuth refresh → UI reauth → manual fallback)
- **Persisted** when dead (tracked for revalidation, not deleted)
- **Secured** end-to-end (no credential exposure at any layer)

Violations of these rules are blockers. The monetizer exits
**MONETIZER_BLOCKED** rather than proceed with a policy violation.
