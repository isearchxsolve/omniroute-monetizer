# Provider / Model Lifecycle — State Machine

## Overview
Every provider and model in OmniRoute transitions through a defined lifecycle.
States are explicit, observable, and driven by API responses. No entity may
skip to VERIFIED without live inference evidence.

---

## States
- **DISCOVERED**: Entity found in registry or upstream catalog. Not yet registered with OmniRoute.
- **REGISTERED**: Entity exists in OmniRoute (`/api/providers`). Credentials may or may not be configured.
- **CREDENTIAL_PENDING**: Provider is registered but requires credentials that are not yet supplied.
- **AUTH_OK**: Credentials validated by `/api/providers/{id}/test` (`valid: true` at connection level).
- **VERIFIED**: Live inference succeeded. A concrete model produced a valid response via `/v1/chat/completions`.
- **DEAD**: Provider or model is non-functional: auth failure, upstream gone, or policy-blocked.
- **COOLDOWN**: Temporary exclusion due to rate limiting (429) or transient errors.
- **POLICY_BLOCKED**: Provider or model is functional but excluded by policy decision.
