# POST-AUDIT FIXES — OmniRoute Monetizer

> **Date:** 2026-08-16
> **Status:** Detailed, ordered fixes for every gap in `POST_AUDIT_GAPS.md`.
> **Ground rules (from AGENTS.md):** No DB hacking — use OmniRoute REST APIs only. No NSSM bounce without user action (non-admin). No fabricating credentials without upstream 200 OK. Sandbox-first for anything risky. Log every action to `MASTER_WORKLOG.md`. Never claim fixed without measured verification.
> **Legend:** 🔴 P0 · 🟠 P1 · 🟡 P2 · Effort = S (≤5 min) / M (≤1 h) / L (1–4 h) / XL (multi-session)

---

## Priority 1 — Security & History Hygiene (G9, G14)

### Fix G9: 🔴 Audit git history for secrets
**Why:** T11 scans the working tree only; worklog entry #19 proves live key material existed in earlier working-tree states, so it may exist in commit history.
**Steps:**
1. Clone-safe scan (never print to terminal): write `scratch/audit_git_history.py` that runs `git log -p --all` and regex-scans for live-key patterns:
   - `sk-or-v1-[A-Za-z0-9]{20,}`, `sk-ant-[A-Za-z0-9_-]{20,}`, `gh[pousr]_[A-Za-z0-9]{20,}`, `nvapi-[A-Za-z0-9_-]{20,}`, `sk-[A-Za-z0-9]{20,}`
   - `STORAGE_ENCRYPTION_KEY[=:]\s*[0-9a-fA-F]{32,}`
   - `password["']?\s*[:=]\s*["'][^"']{8,}`
   - `apikey`/`api_key`/`token` assignments with 20+ char values
2. Output: `state/git_secret_audit.json` (redacted: `key-id: <hash-prefix>`, `commits: [...]`, `files: [...]`). T11-compliant.
3. For every hit: hash-match current live values. If any live value appears in history → treat as **burned**: rotate at the source (provider dashboard / OmniRoute), then purge history via `git filter-repo` + force-push, or worst case rewrite history and update the remote.
4. Do NOT rewrite history while any consuming service still uses an old key — rotate first, then purge.

**Verification:** `state/git_secret_audit.json` exists with zero live-key matches, or all matches listed as rotated.

### Fix G14: 🟡 Encrypt the locally-stored management password
**Why:** `state/omniroute_password.txt` is plaintext on disk.
**Steps:**
1. Create `scripts/automation/password_vault.py`:
   - Encrypt a secret with a DPAPI-derived key (Windows `crypt32` via `ctypes` `CryptProtectData`/`CryptUnprotectData`) — no external deps, decryptable only on this machine+user.
   - Store to `state/omniroute_password.bin`; delete the `.txt` once verified.
   - Fallback chain: env `OMNIROUTE_PASSWORD` → DPAPI vault file → existing scratch fallback (kept for compatibility, logged as deprecated).
2. Update `oauth_keepalive.py` + `omniroute_api.py` password resolution to use the vault (same interface: a `resolve_password()` helper).
3. Leave `d:\omniroute-chrome-profile` where it is but document it in the backup strategy (Fix G10) — it's a live-session copy, encryption is out of scope.

**Verification:** `state/omniroute_password.txt` gone; `oauth_keepalive.py --once` still works using the vault.

---

## Priority 2 — Performance Without Waiting for Upstream (P3, P4, G2, P5)

### Fix P3: 🟠 Caching reverse proxy in front of :20128 (SWR today, on 3.8.49)
**Why:** Reproduces v3.8.50's stale-while-revalidate behavior with zero code changes and zero NSSM bounces. Clients get cached responses even while the event loop is frozen.
**Steps:**
1. Install Caddy (single static binary, no config language to learn for this use) — or Nginx if the user prefers. Caddy recommended: `winget install Caddy.Caddy` or download binary.
2. `Caddyfile` (next to the repo, gitignored copy at `config/caddy/Caddyfile`):
   ```
   :20230 {
       reverse_proxy 127.0.0.1:20128
       @models path /v1/models
       handle @models {
           reverse_proxy 127.0.0.1:20128 {
               # SWR: serve stale up to 601s while background-refreshing
               flush_interval -1
           }
       }
       # Optional: file_server static cache for /_next/static (check actual OmniRoute asset paths first)
   }
   ```
   > **Important:** verify OmniRoute-SSE and streaming routes (chat completions) bypass caching — only `GET`-safe, JSON catalog endpoints (`/v1/models`, `/api/providers` for read-only) may be cached. Never cache `/v1/chat/completions` or any SSE.
3. Configure headers: pass through `Authorization`; set `Cache-Control` only on catalog endpoints; add `X-Cache: HIT/MISS` response header for observability.
4. Point the client integrations (Zed, Codex, tests) at `http://localhost:20230` — **or** change nothing and add Caddy only as an internal latency shield for the acceptance probes.
5. Wire a `Cache-Control: max-age=60, stale-while-revalidate=600` response header for `/v1/models` responses so intermediate caches behave.

**Verification:** continuous probe against :20230 over one rebuilt window shows **zero** sub-route timeouts even when :20128 freezes 24–38s.

**Risk:** low; additive, reversible by stopping Caddy.

### Fix P4: 🟠 Explain the gap between ~24ms warm hits and ~2.05s steady-state
**Why:** Determines whether there's a second per-request hog (P2 pricing N+1) or just hardware.
**Steps:**
1. `scratch/probe_residual_latency.py` — 20 sequential `GET /v1/models` at 10s spacing (outside TTL window mostly), record p50/p95/max + HTTP status. Also time `GET /v1/models` with and without `Authorization` header.
2. Repeat with the pricing endpoint probed in isolation if identifiable (`GET /api/providers/.../models` or whatever raw query `getModelsDevPricing` maps to — check bundle references from #22 §9).
3. Correlate with `service-stderr.log` around each slow sample: `[MODEL]` debug bursts = catalog work, `[AUTO]` = pool rebuild, `[CredentialHealth]`/`[HealthCheck]` = sweepers (should be absent — flags verified dead).

**Verification:** A written conclusion in the worklog entry — either "hardware-bound steady state, ~2s is now the floor for catalog reads" or "pricing N+1 confirmed as a per-request cost", with the measurement table.

### Fix G2: 🟠 Deactivate the dead `auto/zai` combo
**Why:** One authenticated API call; removes dead weight from every auto-combo pool rebuild (worklog #23).
**Steps:**
1. Identify the combo id: `GET /api/combos` → find `auto/zai` (or the `zai` family alias).
2. `PUT /api/combos/{id}` with `{"isActive": false}` (verify exact field name against `scripts/automation/omniroute_api.py` — read it first; do not guess).
3. Confirm with `GET /api/combos`; confirm the `[AUTO] auto/zai matched no connected models` warning stops appearing in logs.
4. If the API rejects deactivation (some versions treat combos as immutable), fall back to removing all models from the combo (empty pool) — verify behavior in the sandbox first.

**Verification:** warning gone from log tail for 1+ rebuild cycle; combos list shows it disabled.

### Fix P5: 🟠 Purge the ~30 dead OAuth connections via supported API
**Why:** Dead rows waste decryption/network work in any future sweep and are the data-rot source.
**Steps:**
1. `GET /api/providers` → list all with `isActive=false` (expected ~30).
2. For each: `POST /api/providers/{id}/test` to confirm still failing; then check whether a `DELETE /api/providers/{id}` endpoint exists in `omniroute_api.py` / the bundle (read the client code first — worklog shows the API surface is `/api/providers/{id}` PUT/POST-based; if DELETE is absent, **do not** touch the DB — document that purge requires the UI and leave it as user action).
3. If DELETE exists: purge, re-test, and confirm count drops.
4. If not: keep suppressed (`isActive=false`) and mark this as "blocked on upstream/UI remove button" — still an improvement because suppression already stops sweeper work.

**Verification:** either provider count drops or a documented "no supported delete path" outcome. Never direct DB edits (AGENTS.md anti-pattern #1).

---

## Priority 3 — Deploy the "Self-Healing" Promise (G4, G5, G6, G2 done above)

### Fix G4 + G5: 🟠 Schedule the existing automation + monitoring
**Why:** Code exists (`health_checker.py`, `provider_orchestrator.py`, `acceptance_tests.py`, `watch_omniroute_release.py`); nothing runs them on a schedule.
**Steps (Windows Task Scheduler, same pattern as the proven `oauth_keepalive_task.bat` from worklog #36):**
1. `scripts/automation/health_watch.py` — thin wrapper around `ProviderHealthChecker` (from `health_checker.py`) that runs a single pass (not a daemon) every 15 min: test active providers, write `state/health_log.json`, exit non-zero on 3+ failures.
   - `.bat` wrapper + `schtasks /create /tn "OmniRoute HealthWatch" /tr "...\health_watch.bat" /sc minute /mo 15`.
2. `scripts/automation/acceptance_watch.py` — runs `acceptance_tests.py --quiet` every 6 h, writes a summary markdown to `state/acceptance_latest.md`, keeps last 30 runs in `state/acceptance_history/`.
   - On regression (non-skip failures appear): append a `MASTER_WORKLOG.md` entry automatically (respecting the entry template) or emit a loud console marker.
3. Release watcher: schedule `scratch/watch_omniroute_release.py` every 30 min (it only polls `npm view`). When v3.8.50 appears in `state/release_watch.json`, that's the upgrade trigger (see Fix G1 below).
4. Stall monitor: convert `scratch/probe_continuous.py` into `scripts/automation/stall_monitor.py` — 3-min pass every 15 min probing `/v1/models`; alert (log + exit code) if any probe >5s during a non-rebuild window.
5. Document all tasks in a new `docs/OPS_RUNBOOK.md` (what runs, interval, where output lands, how to check health in 30 seconds).

**Verification:** `schtasks /query` shows the 4 tasks; two consecutive runs produce `state/health_log.json` + `state/acceptance_latest.md` with sane content.

### Fix G6: 🟠 Wire the verified OpenRouter key into at least one combo as a fallback
**Why:** NVIDIA is the sole provider in all 13 combos; OpenRouter is verified healthy (worklog #35: 363ms, valid=true) and unused.
**Steps:**
1. Confirm OpenRouter connection id + authType (apikey) from `GET /api/providers` (worklog #35: `49aa144d-9005-4968-a6cd-a36e8a2e947f`).
2. Pick the combo with the largest headroom (`auto/best-chat` or `fusion-coder`) and append an OpenRouter model entry as a **weight-0 fallback** entry:
   ```
   { "id": "<new-uuid>", "kind": "model", "model": "<openrouter-model>", "providerId": "openrouter", "weight": 0 }
   ```
   (Match the exact schema used by all 13 combos — read `scratch/fix_combo_providerid.py` / `repair_old_combos_db.py` output first. Use `GET /v1/models` to pick a real, currently-serving OpenRouter model.)
3. Verify the combo routes to NVIDIA, then simulate NVIDIA failure by temporarily deactivating the NVIDIA target (in a **sandbox** first), and confirm the OpenRouter fallback serves 200.
4. Keep the change minimal and log it — this is a design change, so also update the "performance invariant" guidance in AGENTS.md/`docs/PROVIDER_POLICY.md` to mention OpenRouter as the designated fallback provider.

**Verification:** failure-injection test in sandbox; live combo returns 200 via NVIDIA with fallback entry present.

---

## Priority 4 — Resilience & Ops (G10, G8, G1, G11, G12, G13, G7)

### Fix G10: 🟠 Scheduled backup of runtime state
**Steps:**
1. `scripts/automation/backup_state.py` + `.bat` + daily `schtasks`:
   - Copy `C:\Users\Admin\.omniroute\storage.sqlite` (+ `-wal`/`-shm` if present) → `d:\omniroute-backups\<date>\` (retain 14 days).
   - Copy repo `state/` (excluding `browser_profile/` heavy dirs if >100MB — keep storage_state.json only) → same backup dir.
   - Copy `state/generated_keys.json`, `state/release_watch.json`, `state/omniroute_password.bin`.
   - Log result to `logs/backup.log`.
2. Restore procedure documented in `docs/OPS_RUNBOOK.md` (stop service → restore files → start service; admin step required, user-run).

**Verification:** two consecutive daily backups; restore dry-run documented (no actual restore unless user requests).

### Fix G8: 🟡 Archive stale reports
**Steps:**
1. Create `archive/reports-2026-08-15/` and move the superseded docs there: `STATUS.md`, `MONETIZER_FINAL_STATUS.md`, `MONETIZER_FINAL_REPORT.md`, `PERFORMANCE_BASELINE/OPTIMIZATIONS/REGRESSION_REPORT.md`, `OMNIROUTE_PERFORMANCE_AUDIT_COMPLETE.md`, `ROOT_CAUSE_ANALYSIS.md`, `COMPREHENSIVE_ROOT_CAUSE_ANALYSIS.md`, `COMPREHENSIVE_AUDIT_AND_FIXES.md` (audit is historical), `ANALYSIS_COMPLETE_SUMMARY.md`, `MASTER_FIX_STRATEGY.md`, `QUICK_FIX_ROADMAP.md`, `DEFERRED_ACTIONS.md`, `AUTONOMOUS_CREDENTIAL_HARVESTING_BREAKTHROUGH.md`, `HANDOFF_PROMPT_PHASE2.md`.
2. Keep at root only: `AGENTS.md`, `MASTER_WORKLOG.md`, `POST_AUDIT_GAPS.md`, `POST_AUDIT_FIXES.md`, `docs/` (active), plus code/tests/scripts.
3. Update `AGENTS.md` certification matrix header to reference the **T1–T20** acceptance suite (`acceptance_tests.py`), not the old 12-test matrix (or add a pointer: "current suite is T1–T20, see acceptance_tests.py").

**Verification:** root is tidy; a fresh agent reading AGENTS.md sees the 20-test pointer and MASTER_WORKLOG as the source of truth.

### Fix G1: 🔴 Manage the v3.8.50 upgrade path (verify watcher; document decision tree)
**Steps:**
1. Verify `scratch/watch_omniroute_release.py` runs cleanly once (read-only `npm view`; no side effects).
2. Document the full upgrade procedure in `docs/OPS_RUNBOOK.md`:
   - Trigger: `state/release_watch.json` shows `3.8.50`.
   - Pre-upgrade: backup (Fix G10), run acceptance suite (baseline must pass), confirm the two `.env` disable flags survive re-read.
   - Upgrade: `npm install omniroute@latest` inside `C:\Users\Admin\AppData\Local\hermes\node\node_modules` (as user or via the NSSM service user), then **user runs `nssm restart OmniRoute`** (non-admin cannot; documented in worklog #21).
   - Post-upgrade: verify banner (no `[HealthCheck]`, `[CredentialHealth]` startup lines if flags still set — or re-evaluate whether to re-enable now that upstream fixed the sweepers), 4× latency probe, full acceptance run, stall monitor 15 min clean.
   - Fallback if branch stalls: revisit the proxy fix (P3) as permanent; re-check every 2 weeks.
3. Add the "no patch on 3.8.49" decision explicitly, citing worklog #25 (unsafe invalidation gap).

**Verification:** runbook section exists; watcher verified working.

### Fix G11: 🟡 De-duplicate legacy scripts
**Steps:**
1. Move `evidence/automation/*` → `archive/legacy-automation-2026-08-16/` (keep for reference) with a README stating they are superseded by `scripts/automation/*`.
2. Grep repo for imports referencing `evidence.automation` or the old filenames — fix any (expect none; they were standalone runs).

**Verification:** no orphan imports; archive folder README clarifies status. This also shrinks the surface for G9-style history leaks going forward.

### Fix G12: 🟠 Reproducible install path
**Steps:**
1. Write `docs/INSTALLATION.md` capturing the *actual* working install (from worklog #31 sandbox + live):
   - Node version (v22.23.2 observed), npm, `npm install omniroute@3.8.49` with `--ignore-scripts` as sandbox-proven.
   - `.env` template (PORT, DATA_DIR, WS ports, INITIAL_PASSWORD, STORAGE_ENCRYPTION_KEY generation, the two disable flags, TTL override step).
   - NSSM service registration commands, AppEnvironmentExtra values (redacted).
   - Post-install: onboard, login, restore settings (cache-config backup path).
2. Pin versions: `package.json` lockfile for the automation scripts' Python deps (`requirements-browser.txt` exists — extend with a full `requirements.txt`).

**Verification:** a fresh directory boots 3.8.49 following the doc alone (test in sandbox).

### Fix G13: 🟡 Scratch cleanup (conservative)
**Steps:**
1. Move the clearly-superseded/retracted probe scripts to `scratch/archive/`: `raise_catalog_ttl.py`, `raise_catalog_ttl2.py` (retracted in #25), the 8 `find_pool_logic*` variants, `fix_combos*` superseded by `repair_old_combos_db.py`, `hardcode_combos.py`, `nuke_rate_limits.py` (AGENTS.md anti-pattern #1 — this one should arguably be deleted, not just archived).
2. Keep all scripts referenced in MASTER_WORKLOG entries (they're the evidence trail) — archive only those with no worklog reference and no current use.
3. Add a `scratch/README.md` explaining the convention: "scratch = evidence trail; archive = dead; scripts/automation = production."

**Verification:** scratch/README exists; archive folder organized; no worklog-referenced script moved.

### Fix G7: 🟡 Human decisions (document only; no action without user)
**Steps:**
1. Anthropic: keep the generated key in `state/generated_keys.json` (gitignored). Document the exact steps to purchase credits + inject (one `PUT /api/providers/{id}`) once billing is added. No further action — blocks on user decision.
2. trae/windsurf: document the re-login flow (reuse `scratch/export_sessions_cdp.py` pattern from #34) as a 10-minute user task; out of scope until user opts in.

---

## Verified Remaining Work Items (from the worklog — already in flight)
- **P1 (#8697/#8987/#9199)** — none until v3.8.50 publishes (Fix G1 governs).
- **P2 (#9685/#10055)** — same; monitor via Fix G4 stall monitor.
- **G3 (adapters)** — after Fix G5 (automation scheduled) and the v3.8.50 upgrade, refresh `provider_key_adapters.py` selectors against current dashboards. P2 priority; depends on user sessions staying fresh (keep-alive + periodic session refresh).

---

## Execution Order (suggested)
1. **G9** git-history secret audit (security first; ~30 min)
2. **G2** deactivate `auto/zai` (5 min)
3. **P4** residual latency probe (30 min)
4. **P3** Caddy proxy (1–2 h incl. verification through a freeze window)
5. **G4+G5** schedule health watch / acceptance watch / release watcher / stall monitor (1 h)
6. **G10** backups (1 h)
7. **G6** OpenRouter fallback in sandbox then live (1 h)
8. **G8 / G11 / G13** repo hygiene (1 h)
9. **G14** password vault (30 min)
10. **G12** installation doc (1 h)
11. **G1 / G7 / G3** — dependent on v3.8.50 release and user decisions

**Total estimated: ~8–10 hours of hands-on work** (excluding anything blocked on v3.8.50 or user decisions).
