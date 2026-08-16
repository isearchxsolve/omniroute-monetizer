# POST-AUDIT GAP ANALYSIS — OmniRoute Monetizer

> **Date:** 2026-08-16
> **Status:** Companion to `POST_AUDIT_FIXES.md` (detailed fixes for every gap listed here)
> **Source context:** Full read of `AGENTS.md` + `MASTER_WORKLOG.md` (entries #1–#36) + full recursive workspace scan.
> **Legend:** 🔴 Critical · 🟠 Major · 🟡 Minor · ✅ Already covered by migration/change (nothing here)

---

## 1. Performance Gaps

### P1. 🔴 Blocker #3 residual — synchronous model catalog rebuild (KNOWN, OPEN)
- **What:** `modelCatalogCacheTtlMs` raised 60000 → 600000 via `PUT /api/settings/cache-config` (worklog #32). The 24–38s synchronous event-loop freeze now recurs every ~10.6 min instead of every ~94s.
- **Evidence:** Worklog #23 (continuous probe: 9 stalls >3s over 480s, ~100s period), #24 (TTL `6e4` default found in `_177w922._.js`; Zod clamp blocks settings raise >60000; upstream fix merged only into unreleased `release/v3.8.50`), #31 (write/read paths unvalidated; raw DB TTL honored per-request), #32 (635s rebuild gap measured post-fix).
- **Impact:** Every route freezes 24–38s once per ~10 min. T2/T3 fail if they land in a stall window.
- **Current mitigation:** TTL raised 10x (verified live). Acceptance suite 19/19 PASS (T16 skip).
- **Real fix:** Upstream v3.8.50 (SWR #8728, memoization #8987, responsiveness #9199). Not publishable today — npm latest is still 3.8.49.

### P2. 🟠 Pricing N+1 hog (#9685/#10055) — LATENT, UNMITIGATED
- **What:** `getModelsDevPricing()` re-runs SQL + re-parses all pricing rows per call, no memoization in 3.8.49 bundle.
- **Evidence:** Worklog #22 §9. `MODELS_DEV_SYNC_ENABLED=0` kill-switch exists only as open PR #10299; 0 chunks in our bundle honor it.
- **Impact:** Request-driven freeze risk. Not the current periodic blocker, but any route touching pricing can freeze the loop. TTL fix does not help.
- **Status:** No clean 3.8.49 mitigation documented.

### P3. 🟠 No caching reverse proxy in front of :20128 — OPENS NEW FIX PATH
- **What:** Nothing sits between clients and `localhost:20128`.
- **Why it matters:** A stale-while-revalidate caching proxy (Caddy/Nginx) can serve `GET /v1/models` and static assets instantly even while the event loop is frozen — reproducing v3.8.50's SWR behavior on 3.8.49 with zero code changes, zero NSSM bounces.
- **Never proposed in the worklog.** This is the strongest low-risk, no-restart performance win available today.

### P4. 🟠 Measured /v1/models steady-state ~2.05s vs. 24ms warm cache hit — UNEXPLAINED
- **What:** Acceptance T14 measures ~24ms on a warm cache hit; continuous probes every 2s show ~2.05s per request.
- **Hypotheses:** Per-request cost surviving the TTL cache (pricing N+1 from P2?), catalog parse outside cached path, or hardware ceiling.
- **Status:** Needs one dedicated probe before attributing to hardware.

### P5. 🟠 ~30 dead OAuth connections still resident in DB
- **What:** Dead connections are `isActive=false` (suppressed) but not purged; ~24 carry undecryptable credentials (`[Encryption] Auth tag validation likely failed`).
- **Impact:** Any future sweep/migration/full rebuild does wasted decryption work on them. Data rot source.
- **Status:** Worklog #18/#21/#22 traced their harm; purge via supported API never executed.

### P6. 🟠 Hardware ceiling — i5-3320M (4 threads) / ~4 GB free RAM
- **What:** CPU-bound cold rebuilds (~35s) and unusable Playwright-launched Chrome on this hardware (worklog #34).
- **Implication:** Even v3.8.50's cooperative yielding leaves cold rebuilds slow. Only lever: reduce per-cycle work (prune connections, deactivate dead combos).

### P7. 🟡 No recurring DB integrity / WAL checkpoint monitoring
- **What:** WAL grew to 4.1 MB during the corruption era; nothing today monitors WAL size, `PRAGMA integrity_check`, or checkpoint health.
- **Evidence:** Worklog #14–#18 (crash loop from WAL corruption + encryption mismatch).
- **Status:** No scheduled check exists.

### P8. 🟡 Memory pressure — 3 GB Node heap against 4 GB limit
- **What:** VM observed at ~3 GB / 4 GB heap with 15.7 GB RAM (4.1 GB free). No GC tuning or heap monitoring.
- **Risk:** Swap/thrash under rebuild + sweep overlap.

---

## 2. General Gaps

### G1. 🔴 Upgrading to v3.8.50 is blocked on upstream publication
- **What:** All real fixes (#8697 SWR, #9180 active-only sweep, token-healthcheck interval fix) merged into `release/v3.8.50`, NOT tagged/published (worklog #24). npm `latest` = 3.8.49.
- **Status:** Watcher `scratch/watch_omniroute_release.py` → `state/release_watch.json` armed. Upgrade path documented (npm install + NSSM bounce) but no fallback if branch stalls.

### G2. 🟠 Dead combo `auto/zai` still registered
- **What:** `auto/zai` family has zero connected models; every auto-combo pool rebuild still walks it, adding to the rebuild cost identified in #23.
- **Status:** Candidate mitigation (deactivate) identified in #23 but never executed.

### G3. 🟠 Provider key adapters stale + only 3/51 providers covered
- **What:** `provider_key_adapters.py` has adapters for ~3 of 51 providers; worklog #35 already observed selector drift (Anthropic console → platform.claude.com, GitHub/OpenRouter UI changes).
- **Status:** "Update adapters to match current DOM" listed as next step in #35; never done.

### G4. 🟠 "Self-healing" is ~40% deployed
- **What:** `health_checker.py` + `provider_orchestrator.py` are code-ready but never integrated or scheduled. Only the OAuth keep-alive (entry #36) runs as a scheduled task. T16 (provider coverage ≥50%) never executed.
- **Impact:** The "No More Daily Fixes" guarantee (entry #11) is not fully delivered as deployed.

### G5. 🟠 No 24/7 monitoring or regression schedule
- **What:** Acceptance suite runs manually. Release watcher not scheduled. Nothing watches overnight for stall recurrence, dead providers, or service crashes.
- **Status:** Monitoring *tooling* exists; monitoring *schedule* does not.

### G6. 🟠 Single-provider dependency — NVIDIA in all 13 combos
- **What:** All 13 combos lean on the NVIDIA family. OpenRouter connection is verified and injected (worklog #35, 363ms, valid=true) but routed into **zero** combos.
- **Impact:** If NVIDIA dies again (it did once — the 503 era), the system is down despite a healthy fallback provider. Design gap #13 (fallback cascade) from Phase 1 audit never implemented.

### G7. 🟡 Open human decisions
- **What:** Anthropic billing (key generated + verified auth, but 400 "credit balance too low" — not injected, #35); trae + windsurf ×2 need OAuth re-login (#36).
- **Status:** Waiting on user. Blocks full provider coverage.

### G8. 🟡 Stale documentation ~25 top-level reports
- **What:** `STATUS.md`, `MONETIZER_FINAL_STATUS.md`, several `PERFORMANCE_*`/`*_RCA_*`/`*_REPORT*` docs contradict current reality (12/12 and MONETIZER_READY claims; acceptance now 20 tests, 19/19). AGENTS.md certifies a 12-test matrix while `acceptance_tests.py` runs 20.
- **Impact:** Resuming agent gets a wrong picture unless it starts at MASTER_WORKLOG.

### G9. 🟠 Secrets-in-git-history never audited
- **What:** T11 scans the working tree only. Worklog entry #19 retroactively redacted keys *from the worklog*, meaning prior states likely contained live values.
- **Impact:** If any commit history contains a real key, it must be treated as burned and rotated — regardless of current tree.
- **Status:** `git log -p` regex scan never run.

### G10. 🟠 No backup strategy for runtime state
- **What:** `storage.sqlite` (outside repo, crashed once), `state/generated_keys.json`, `state/release_watch.json`, `state/browser_profile`, `d:\omniroute-chrome-profile` — none under recurring backup; only one-off manual backups exist.
- **Evidence:** Worklog #14–#18 (DB corruption), #34 (profile copy created manually).

### G11. 🟡 Duplicated/legacy script versions
- **What:** `evidence/automation/` holds v10/v11/v12 superseded scripts with same names as live `scripts/automation/*`.
- **Impact:** Run-the-wrong-file risk; potential leakage source (ties to G9).

### G12. 🟠 No reproducible install path
- **What:** OmniRoute lives in `hermes/node_modules` with no lockfile/pinned deps doc; no recreate-from-scratch procedure in repo (sandbox was built ad hoc in `d:\omniroute-sandbox`).
- **Impact:** Disk failure → non-reproducible reinstall.

### G13. 🟡 Scratch clutter (~190 scripts)
- **What:** Huge investigative trail with superseded/contradictory variants (`find_pool_logic*` ×8, `raise_catalog_ttl*` ×2 where one proposal was retracted).
- **Impact:** Maintenance/confusion cost; some one-off probes could be archived.

### G14. 🟡 Secrets management hygiene
- **What:** `state/omniroute_password.txt` stores management password plaintext on disk (gitignored, unencrypted). Live Chrome profile copy at `d:\omniroute-chrome-profile` holds authenticated sessions.
- **Impact:** Unencrypted and one deletion/blip away from locking us out.

---

## 3. Priority Order

| # | Gap | Justification |
|---|-----|---------------|
| 1 | G9 | History secret leak = burned credentials, security issue |
| 2 | P3 | Masks the last blocker on 3.8.49 without waiting for upstream |
| 3 | P4 | Understand the 2s residual before claiming "fixed" |
| 4 | G2 | One API call; reduces every rebuild's work |
| 5 | G4 + G5 | Turn existing code into scheduled services (self-healing promise) |
| 6 | G10 | DB already corrupted once; no recurring backup is indefensible |
| 7 | G6 | Wire OpenRouter fallback into combos |
| 8 | G8 | Stop the wrong-picture trap for resuming agents |
| 9 | P5 | Purge dead OAuth rows via supported API |
| 10 | P1/P2 | Only truly solvable by v3.8.50 — verify watcher, keep monitoring |
| 11 | G7, G11, G12, G13, G14 | User decisions / hygiene |

---

*Detailed fixes for every gap: see `POST_AUDIT_FIXES.md`.*
