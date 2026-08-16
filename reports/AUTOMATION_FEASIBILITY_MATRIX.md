# Automation Feasibility Matrix — 2026-08-16

Ground-truth recon results for the remaining automation phase (T16 / initial-phase scope).
All findings from read-only probes — no clicks, no injections, no key creation.

## Tier A — CLI / local token harvest (NO browser needed)

Run: `scratch/run_harvest_dryrun.py` (wraps `scripts/automation/cli_token_harvester.py --dry-run`)

| Source | Provider | Upstream verify | OmniRoute action |
|---|---|---|---|
| env:OPENROUTER_API_KEY | openrouter | ✅ 200 OK | idempotent skip (connection already active) |
| env:NVIDIA_API_KEY | nvidia | ✅ 200 OK | idempotent skip (connection already active) |
| gh-cli (`gh auth token`) | github | ✅ 200 OK | skipped — GitHub connections are OAuth-only, no apikey connection (correct per policy) |
| env:ANTHROPIC_API_KEY | anthropic | ❌ 401 | dead key — needs fresh key (Tier B/C) |
| env:OPENAI_API_KEY | openai | ❌ 401 | dead key — needs fresh key (Tier B/C) |

**Verdict: Tier A machinery is COMPLETE and working.** 3/5 verified, idempotency proven,
OAuth connections correctly untouched. Nothing to build here — only to schedule (cron/task).

## Tier B — DOM dashboard automation (browser, no vision)

DOM machinery **proven working**: `scratch/dom_recon.py` captured full structured snapshots
(buttons, inputs, headings, body text) of all 3 dashboards headlessly via the persistent profile.
The DOM approach is sound — zero vision needed, deterministic selectors available.

| Provider | Dashboard | Session state | Verdict |
|---|---|---|---|
| OpenRouter | openrouter.ai/keys | **FRESH (entry #34)** | ✅ **AUTHENTICATED** → /workspaces/default/keys |
| Anthropic | console.anthropic.com/settings/keys | **FRESH (entry #34)** | ✅ **AUTHENTICATED** → platform.claude.com/settings/keys |
| GitHub | github.com/settings/tokens | **FRESH (entry #34)** | ✅ **AUTHENTICATED** → /settings/tokens |

**Verdict (UPDATED entry #34): Tier B is UNBLOCKED.** All 3 sessions refreshed via plain-Chrome
+ CDP export (Playwright-interactive was abandoned — unusably slow on this i5-3320M/HD4000
hardware). Sessions verified headless read-only in `state/dom_recon/session_verify.json`.
The DOM adapters (`provider_key_adapters.py`) can now run autonomously against
`state/browser_profile/storage_state.json`.

## Tier C — key generation EXECUTED (entry #35)

Autonomous key generation was run for all 3 providers against the fresh sessions.
Method: read-only surface/dialog capture → mutating key-gen → upstream verify (200 OK
required, anti-pattern #7) → inject. Full keys only in gitignored `state/generated_keys.json`.

| Provider | Key generated | Upstream verify | Injected into OmniRoute | Outcome |
|---|---|---|---|---|
| OpenRouter | ✅ `sk-or-v1-1...f00a` (len 73) | ✅ 200 OK | ✅ conn `49aa144d…` → test valid=true, 363ms | **DONE** |
| Anthropic | ✅ `sk-ant-api03...OgAA` (len 108) | ❌ 400 "credit balance too low" | ❌ not injected (no 200 OK) | **BILLING WALL** — free "Evaluation access" plan, no credits |
| GitHub | ✅ `ghp_qoci...e2d0` (len 40) | ✅ 200 OK (`api.github.com/user`) | ❌ not injected | **WRONG CREDENTIAL TYPE** — OmniRoute GitHub conn is authType=oauth (Copilot token), already testStatus=active; classic PAT doesn't fit |

**Verdict (entry #35):** Tier C key-gen machinery WORKS end-to-end (DOM capture → create →
capture plaintext → verify → inject). OpenRouter fully wired. Anthropic blocked on billing
(human decision: add credits). GitHub connection already healthy via Copilot OAuth — a
classic PAT is not applicable; injecting it would corrupt a healthy OAuth connection
(anti-pattern #1).

Still blocked / human-in-loop:
- OAuth login flows (Google/Apple/SSO) — handled via user-driven session refresh (entry #34)
- CAPTCHA / MFA / sudo-mode password re-entry (GitHub token creation had NO sudo wall this run)
- TokenRouter: no account/session exists; placeholder injection is FORBIDDEN (anti-pattern #7)

## Honest capability summary

| Tier | Confidence | Status |
|---|---|---|
| A — CLI harvest | High | ✅ DONE, verified, idempotent |
| B — DOM key creation | High | ✅ DONE — sessions refreshed (entry #34), key-gen executed (entry #35) |
| C — OAuth/MFA | Medium | 🟡 key-gen works; Anthropic billing-walled; GitHub conn already healthy via OAuth |

## Next steps

- **Anthropic:** requires a human billing decision (add credits / upgrade plan) before its key can pass upstream verification and be injected. Key is saved in `state/generated_keys.json`.
- **GitHub:** no action needed — the Copilot-OAuth connection is already active/healthy.
- **Selector maintenance:** `scripts/automation/provider_key_adapters.py` selectors are STALE vs current DOM (Anthropic moved to platform.claude.com; expiration is a role=combobox). The working current selectors live in `scratch/keygen_*.py` — port them back into the adapters before the next autonomous run.
- Session refresh (when cookies expire): plain Chrome on `d:\omniroute-chrome-profile` + `--remote-debugging-port=9222` + `scratch/export_sessions_cdp.py` (entry #34 pattern).

## Artifacts

- `state/dom_recon/openrouter_recon.json`, `anthropic_recon.json`, `github_recon.json` — full DOM snapshots
- `state/dom_recon/recon_summary.json` — verdicts
- `state/harvest_result.json` — Tier A dry-run results (tokens redacted)
- `scratch/dom_recon.py`, `scratch/run_harvest_dryrun.py`, `scratch/inspect_browser_state.py`
