# Master Monetizer V1 Specification

## Inputs
- D:\omniroute-phase-a\AGENTS.md
- D:\omniroute-phase-a\CODEX_HANDOFF.md
- automation/
- registry/
- results/
- live OmniRoute state
- current Zed/Codex/Claude Code state
- supplied omniroute_full_setup.py

## Canonical outcomes
### Runtime
- preserve the existing working OmniRoute runtime
- never restart the running service

### Providers
- keep provider/account/credential/model/route identities distinct
- preserve healthy connections
- never fabricate credentials

### Routing
FRONTIER
- alias: frontier
- Frontier-only
- no silent lower-tier fallback

PRO CODING
- auto/pro-coding

PRO REASONING
- auto/pro-reasoning

PRO CHAT
- auto/pro-chat

BEST/FAST/FREE
- preserve only what is actually verified/working
- never claim free entitlement from metadata alone

### Verification
Use minimal exact-response smoke tests. No mass model probing.

### Client integration
- Zed -> local OmniRoute
- Zed Frontier entry sends model ID `frontier`, not `auto/frontier`
- Codex and Claude Code -> live OmniRoute
- preserve unrelated client settings

### Reporting
Reports must be sanitized and contain no credentials.

## Browser/DOM automation

The implementation must contain a reusable browser engine that:
- discovers provider UI structure;
- detects re-auth/refresh controls;
- performs only explicitly safe UI actions automatically;
- stops for MFA/CAPTCHA/consent/manual credential generation;
- resumes via API test after human handoff;
- writes sanitized artifacts.

Provider-specific adapters may override URL/slug/control semantics without
duplicating the entire browser engine.
