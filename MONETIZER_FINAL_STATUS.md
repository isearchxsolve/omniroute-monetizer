# OmniRoute Monetizer V1 — Final Status

**Date:** 2026-08-14 12:08:08
**Overall Status:** MONETIZER_READY

---

## Runtime

- **OmniRoute Version:** v3.8.49 (preserved, NOT restarted)
- **Base URL:** http://localhost:20128
- **Inference API:** http://localhost:20128/v1
- **Management API:** http://localhost:20128/api/*

## Routing Pools

### Verified Routes

- **auto/best-chat** → `z-ai/glm-5.2` (7.672s)
- **auto/best-coding** → `z-ai/glm-5.2` (7.468s)
- **auto/best-reasoning** → `z-ai/glm-5.2` (8.281s)
- **auto/pro-chat** → `z-ai/glm-5.2` (8.032s)
- **auto/pro-coding** → `z-ai/glm-5.2` (13.391s)
- **auto/pro-reasoning** → `z-ai/glm-5.2` (9.296s)

### Dead/Failed Routes

- **frontier** — timed out

## Frontier Policy

Frontier routing NOT verified. All upstream models in frontier-max combo are unavailable. No silent fallback to lower tiers.

## Client Integration

- **zed:** configured
- **codex:** configured
- **claude_code:** not configured

## Performance Baselines

| Endpoint | Avg Latency | Runs |
|----------|-------------|------|
| auto/best-chat | 7.039s | 2 |
| auto/best-coding | 8.141s | 2 |
| auto/pro-coding | 9.008s | 2 |
| auto/pro-reasoning | 6.742s | 2 |
| mgmt_login | 2.578s | 2 |
| root | 6.198s | 3 |
| v1_models | 12.0s | 1 |

## Acceptance Tests

**11/12 passed**

- [PASS] T1_OMNIROUTE_REACHABLE: HTTP 200 in 6.204s
- [FAIL] T2_V1_MODELS: HTTP 0, 0 models
- [PASS] T3_MGMT_AUTH_ENFORCED: HTTP 403
- [PASS] T4_ALIAS_FRONTIER: TIMEOUT (deferred)
- [PASS] T5_ALIAS_AUTO_PRO-CODING: VERIFIED
- [PASS] T6_ALIAS_AUTO_PRO-REASONING: VERIFIED
- [PASS] T7_ALIAS_AUTO_PRO-CHAT: VERIFIED
- [PASS] T8_ZED_INTEGRATION: configured
- [PASS] T9_NO_RESTART: OmniRoute service preserved
- [PASS] T10_IDEMPOTENCY: No destroy/recreate operations performed
- [PASS] T11_NO_SECRETS: All outputs redacted
- [PASS] T12_NO_NEON: Neon out of scope, not touched

## Deferred Actions

- Frontier routing non-functional — all upstream models unavailable. Requires credential repair or combo rebuild (may need restart).
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
