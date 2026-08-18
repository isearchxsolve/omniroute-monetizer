# OmniRoute Monetizer Gap Analysis Blueprint
Generated: $(date -Iseconds)

## Executive Summary
- **TOTAL providers in ledger**: 296
- **LIVE_VERIFIED (E2E with content proof)**: 17
- **OAUTH_ACTIVE (valid OAuth session)**: 7
- **EXTERNAL_ACCOUNT_REQUIRED (needs API key / OAuth signup)**: 183
- **WEB_COOKIE_REQUIRED (needs harvested browser session/cookie)**: 23
- **NOAUTH_LOCAL_CLI_MISSING (requires local CLI binary)**: 13
- **NOT_CHAT_COMPLETABLE (non-LLM service kinds)**: 32
- **Remaining gaps**: each ≤5 providers

## Gap Taxonomy & Counts
$(python -c "
import json
with open('state/evidence/gap_analysis.json') as f:
    ga = json.load(f)
for g, info in ga['gap_summary'].items():
    print(f'- {g}: {info[\"count\"]} providers')
")

## Actionable Buckets (Next-Step Work)
$(python -c "
import json
with open('state/evidence/gap_analysis.json') as f:
    ga = json.load(f)
for bucket, slugs in ga['actionable_buckets'].items():
    if slugs:
        print(f'\\n### {bucket} ({len(slugs)} providers)')
        print('Examples:', ', '.join(slugs[:8]))
        if len(slugs) > 8:
            print(f'  ... and {len(slugs)-8} more')
")

## Evidence Appendix
Full evidence bundles are available in:
- `state/evidence/provider_evidence_static.json`   (registry + ledger + catalog)
- `state/evidence/provider_evidence_dynamic.json`  (connection tests + bounded E2E + log errors)
- `state/evidence/provider_evidence_noauth.json`   (noAuth/connectionless probes)
- `state/evidence/provider_evidence_consolidated.json` (per-provider gap + evidence)
- `state/evidence/gap_analysis.json`               (this summary + actionable buckets)

## Methodology (User-Mandated)
1. **Static extraction**: parsed every provider TS registry file, executor inventory, ledger, live connections, live catalog.
2. **Dynamic sweep**: test_connection on all 62 live connections, bounded E2E probes on active connections, app.log error extraction.
3. **NoAuth probes**: probed all connectionless LLM-kind noAuth providers.
4. **Consolidation**: merged evidence, classified each provider into one gap using evidence-first rules.
5. **Actionable buckets**: derived next-step work from gaps (re-auth, add API key, harvest cookie, install CLI, etc.).

## Zero-Fabrication Rule (T11)
- No secrets ever written to logs or evidence files (apiKey values redacted to presence booleans).
- LIVE status requires real HTTP 200 with non-empty content proof from `/v1/chat/completions`.
- All gaps are backed by at least one piece of evidence (test, E2E, log, registry).

## Next Actions
1. Distribute this blueprint to the team.
2. Tackle the **QUICK_WINS** buckets first (re-auth OAuth, add missing API keys).
3. Execute the **WEB_COOKIE_harvest** bucket using the proven Google SSO blueprint.
4. Address **MODEL_DRIFT_fix_names** by updating model aliases in the registry.
5. For **LOCAL_CLI_install** providers, evaluate bundling the CLI or documenting the prerequisite.
6. Monitor **EXTERNAL_ACCOUNT_signup** providers for partnership/API-key programs.