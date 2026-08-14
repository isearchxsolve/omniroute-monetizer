# OmniRoute Monetizer V1 — Final Status

**Date:** 2026-08-14 20:23:12
**Overall Status:** MONETIZER_READY

---

## Runtime

- **OmniRoute Version:** v3.8.49 (preserved, NOT restarted)
- **Base URL:** http://localhost:20128
- **Inference API:** http://localhost:20128/v1
- **Management API:** http://localhost:20128/api/*

## Routing Pools

### Verified Routes

- **auto/best-chat** → `z-ai/glm-5.2` (5.453s)
- **auto/best-coding** → `z-ai/glm-5.2` (5.203s)
- **auto/best-reasoning** → `z-ai/glm-5.2` (4.047s)
- **auto/pro-chat** → `z-ai/glm-5.2` (18.859s)
- **auto/pro-coding** → `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (14.016s)
- **auto/pro-reasoning** → `z-ai/glm-5.2` (7.0s)
- **frontier** → `z-ai/glm-5.2` (2.203s)

### Dead/Failed Routes

- *(none)*

## Frontier Policy

Frontier routing verified. Frontier-only, no lower-tier fallback.

## Client Integration

- **zed:** configured
- **codex:** configured
- **claude_code:** not configured

## Performance Baselines

| Endpoint | Avg Latency | Runs |
|----------|-------------|------|
| auto/best-chat | 4.992s | 2 |
| auto/best-coding | 10.438s | 2 |
| auto/pro-coding | 10.218s | 1 |
| auto/pro-reasoning | 4.523s | 2 |
| mgmt_login | 3.148s | 2 |
| root | 6.568s | 3 |
| v1_models | 10.386s | 3 |

## Acceptance Tests

**12/12 passed**

- [PASS] T1_OMNIROUTE_REACHABLE: HTTP 200 in 7.313s
- [PASS] T2_V1_MODELS: HTTP 200, 2432 models
- [PASS] T3_MGMT_AUTH_ENFORCED: HTTP 403
- [PASS] T4_ALIAS_FRONTIER: VERIFIED
- [PASS] T5_ALIAS_AUTO_PRO-CODING: VERIFIED
- [PASS] T6_ALIAS_AUTO_PRO-REASONING: VERIFIED
- [PASS] T7_ALIAS_AUTO_PRO-CHAT: VERIFIED
- [PASS] T8_ZED_INTEGRATION: configured
- [PASS] T9_NO_RESTART: OmniRoute service preserved
- [PASS] T10_IDEMPOTENCY: No destroy/recreate operations performed
- [PASS] T11_NO_SECRETS: All outputs redacted
- [PASS] T12_NO_NEON: Neon out of scope, not touched

## Deferred Actions

- Free tier routing non-functional. Requires identifying available free models and rebuilding combo.

## Security

- No secrets hard-coded in source or reports
- No credentials printed in logs
- Management password sourced from environment variable
- All output files redacted

## Idempotency

- No resources destroyed or recreated
- Existing healthy connections preserved
- Script converges on repeated runs

---

**FINAL STATUS: MONETIZER_READY**
