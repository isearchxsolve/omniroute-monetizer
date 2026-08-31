# MANDATORY: OmniRoute Monetizer Acceptance State Machine

This rule is injected into every Kilo Code mode working in this repository. The worker's prose is never an acceptance decision. An artifact may only be reported at the highest state its evidence supports; when uncertain, use the lower state.

## Evidence states

```text
UNSEEN
  -> SSO_INITIATED
  -> SSO_PROVIDER_SESSION_OBSERVED
  -> ONBOARDING_VERIFICATION_REQUIRED
  -> FINAL_PROVIDER_SURFACE_OBSERVED
  -> PROVIDER_ACTION_VERIFIED
  -> SIGNUP_COMPLETED
  -> SESSION_CAPTURED
  -> PYTHON_GRADUATED
  -> ROUTE_ATTRIBUTED
  -> CAPACITY_ADMITTED
```

## Required interpretation

- Google account selection or consent proves only `SSO_INITIATED`.
- A post-SSO redirect and token-shaped cookies prove at most `SSO_PROVIDER_SESSION_OBSERVED`.
- An onboarding, survey, verification, loading, subscription-wall, quota, CAPTCHA, OTP, password, or MFA surface blocks advancement and must be reported as `ONBOARDING_VERIFICATION_REQUIRED` or the specific wall.
- `SIGNUP_COMPLETED` requires provider-specific account-creation evidence and a final non-wall provider surface.
- `PROVIDER_ACTION_VERIFIED` requires a successful harmless provider operation.
- `PYTHON_GRADUATED` requires a fresh pure-Python adapter execution without Chrome at runtime.
- `ROUTE_ATTRIBUTED` requires the response to identify provider and session through the canonical endpoint `http://127.0.0.1:8190/v1`.
- `CAPACITY_ADMITTED` requires all preceding evidence plus a healthy fresh re-probe, counted as provider/account × model family × harness × modality.

Inventory, model listings, screenshots, redirects, cookie names, tab presence, generated code, and worker prose are never capacity by themselves.

## Forbidden claims

Do not write “signup completed,” “new account,” “working,” “healthy,” “graduated,” or “capacity” without the corresponding state, timestamp, endpoint, harness, modality, and evidence reference. A balanced pool response must not be credited to a pinned provider unless the response attribution proves that provider.

## Safety boundaries

Never type passwords, OTPs, or email-verification codes; never bypass CAPTCHA, MFA, quota, payment, or provider safety walls. Never attach automation to the operator's live Chrome profile. Never restart or replace task-owned services as a workaround for a stale report.
