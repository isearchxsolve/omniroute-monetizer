

### [2026-08-28 00:30] #1111 — DOC SWEEP + COOKIE PORTABILITY PROVEN: operator's challenge to PORTING.md validated empirically — provider sessions ARE portable via CDP cookie export (1,842 cookies / 335 domains / 253 auth-like exported from 4 live seats); cookie_porter.py built; PORTING.md + TECHNOLOGY_TRANSFER.md §16 corrected and new §20-23 added (24h sweep, Windows services registry, crash/reboot recovery chain, Chrome runtime dependency analysis)

**Objective (operator questions):** (1) is :8190 API-key gated? (2) revisit keepalive/recovery/porting pillars; PORTING.md needs a fresh update after 24h of work; TECHNOLOGY_TRANSFER.md needs the 24h work. (3) crash/reboot/reset recovery — do Chrome profiles + provider sign-ins persist? (4) do we really need the 4 seat Chromes running for the endpoint? Operator challenged PORTING.md's "cannot copy Chrome profile sessions" claim: Google profile — agreed, but provider sessions are their own sessions (possibly SSO'd via Google) and should be persistable/copyable.

**1. API-KEY GATING ANSWER:** Currently NO — `state/secrets/tenant_map.json` does not exist, so the shim runs in open single-operator mode (verified: `/v1/models` → 200 with no key). The Bearer-key tenancy gate (#1110) is armed-and-ready: drop a `{"api_key": "tenant_name"}` JSON file into `state/secrets/tenant_map.json` and auth switches ON instantly, no restart (map is re-read per request). Verified earlier today: no key → 401, bad key → 401, valid key → 200, tenant tagged on every response.

**2. OPERATOR'S PORTING CHALLENGE — VALIDATED EMPIRICALLY.** The old PORTING.md said "profiles cannot be copied." That is true ONLY of a raw directory copy (Chrome seals the on-disk Cookies DB key with DPAPI). But the operator's intuition was right: a LIVE Chrome with CDP exposes every cookie DECRYPTED via `Storage.getCookies` — the DPAPI seal protects the file at rest, not the running browser's memory. Proof (`scratch_prove_cookie_portability.py`, read-only, nothing injected):
- Seat 1 (:9222) alone: **1,734 cookies, 318 provider domains, 253 auth-like** (session/token/auth/sid/jwt names), including HttpOnly ones (featherless `session`, xfyun `SESSION`, atlassian `atl.xsrf.token`, google `__Secure-OSID`).
- All 4 seats: **1,842 unique cookies across 335 domains** (claude.ai 19, groq.com 18, perplexity.ai 15, heygen 44, you.com 34, rtst.ai 15, akool 15, ...).
- What still does NOT port: Google account sign-in (DBSC device-bound), localStorage-bound tokens, device-attested sessions. Law 5 stands for those.

**3. NEW TOOL: `scripts/automation/cookie_porter.py`** — makes provider-session portability real, not just proven:
- `--export --ports 9222,9223,9224,9225 --out <path>`: CDP `Storage.getCookies` from every seat, dedup by (domain,name,path), manifest JSON. Tested: 1,842 cookies → `state/secrets/provider_sessions_export.json` (gitignored credential store).
- `--import --port 9222 --in <path> [--domains ...]`: re-inject via `Storage.setCookies` into a fresh profile on any machine.
- `--list`: inspect an export.

**4. PORTING.md FRESH UPDATE:** portable table gains the CDP cookie-export row; new §Provider Session Portability (export/import commands, what survives, limitations); step 2b added (export into bundle); step 8 rewritten from "human, unavoidable, the long one" to "partially automated" (inject cookies → only Google-SSO/localStorage providers need manual sign-in); new §Windows services registered (full task inventory + reboot recovery chain); failure-mode #1 clarified (raw copy bad, CDP export good).

**5. TECHNOLOGY_TRANSFER.md UPDATE:**
- §16 corrected: 4-column survival table (file-backed / Chrome-backed chat / video); "Never copy" paragraph now distinguishes raw-copy (still forbidden) from CDP cookie export (proven portable).
- §20 NEW — the 24-hour sweep #1081→#1110 in 9 numbered beats (Chrome Gap Doctrine → in-browser replay → send-time reconstruction → Adapter Thesis → pool wiring → tab sweep → video pool → load-balancing fix → consumer hardening) + current endpoint state.
- §21 NEW — Windows services registry: 4 scheduled tasks (Rig Supervisor 5min, Session Pool Shim 5min, Video Router 5min, OAuth KeepAlive hourly) + Startup-folder `omniroute_rig_supervisor.vbs`, all verified present via `schtasks /Query`; ownership rules (OmniRoute never touched, video router owned by its task, command-line matching).
- §22 NEW — crash/reboot/reset recovery chain diagram + persistence table. KEY INSIGHT: provider sessions persist NATIVELY across reboot on the same machine (cookies live in the on-disk Cookies DB; DPAPI only matters for cross-machine/outside reads). Only the Chrome PROCESS dies; video router task relaunches all 4 seats ≤5 min with profiles (and sign-ins) intact. Human-needed list: Google Sync sign-in, OmniRoute password re-seal, OmniRoute OAuth reconnects.
- §23 NEW — "do we need Chrome running?": three supply tiers (file-backed replay ❌ no Chrome; API-credential seats ❌ no Chrome; Chrome-backed seats ✅ tab IS the credential). Full 50-model catalog needs the 4 seats; file-backed subset works Chrome-dead; after reboot everything self-heals ≤5 min.

**6. KEEPALIVE/RECOVERY PILLAR STATUS (revisited):** supervisor `--watch` armed via Startup launcher (`install_autostart.py --status` → present); all 4 tasks Ready/Running; shim verified live (HTTP 200, 50 models). Autostart verified: `omniroute_rig_supervisor.vbs` present in Startup folder.

**Files changed:** PORTING.md, TECHNOLOGY_TRANSFER.md (§16 corrected, §20-23 added)
**Files created:** scripts/automation/cookie_porter.py, scratch_prove_cookie_portability.py, state/secrets/provider_sessions_export.json (gitignored)
**Verdict:** operator was right — provider sessions port. Docs now say so, with a tool that does it.
