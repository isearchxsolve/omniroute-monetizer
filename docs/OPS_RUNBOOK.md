# OmniRoute Monetizer — Operations Runbook

> The single operations reference for the production OmniRoute Monetizer.
> Complements `MASTER_WORKLOG.md` (audit trail) and `docs/INSTALLATION.md` (install).
>
> **Ground rules (AGENTS.md):** never restart/kill the service from automation
> (admin/user-run NSSM bounce only); no DB hacking; secrets never logged (T11);
> accept as fact the documented residual blocker #3 (synchronous catalog rebuild)
> until v3.8.50 ships.

---

## 0. Health check in 30 seconds

```powershell
# 1. Service alive
curl -s -o NUL -w "%{http_code}" http://127.0.0.1:20128/          # expect 200

# 2. Any recent stalls? (last stall_monitor pass)
Get-Content d:\omniroute-monetizer\state\stall_monitor_result.json | ConvertFrom-Json

# 3. Any provider failures? (last health_watch pass)
Get-Content d:\omniroute-monetizer\state\health_log.json | ConvertFrom-Json

# 4. Acceptance still green? (last acceptance_watch pass)
Get-Content d:\omniroute-monetizer\state\acceptance_latest.md

# 5. Did the OAuth keep-alive run recently?
Get-Content d:\omniroute-monetizer\state\keepalive_result.json | ConvertFrom-Json
```

All five state files live in `d:\omniroute-monetizer\state\` and are written by
the scheduled tasks below.

---

## 1. Production component map

| Component | Runs | Interval | Output | Alert on |
|---|---|---|---|---|
| OmniRoute service (NSSM) | always | — | `C:\Users\Admin\.omniroute\logs\service-*.log` | crash / watchdog exit |
| `oauth_keepalive.py --once` | Task Scheduler | 15 min | `logs\keepalive.log`, `state\keepalive_result.json` | 3+ OAuth failures |
| `health_watch.py` | Task Scheduler | 15 min | `logs\health_watch.log`, `state\health_log.json` | ≥3 failed connections |
| `stall_monitor.py` | Task Scheduler | 15 min (3-min pass) | `logs\stall_monitor.log`, `state\stall_monitor_result.json` | >1 slow probe per pass |
| `release_watch.py` (scratch) | Task Scheduler | 30 min | `state\release_watch.json` | version ≥3.8.50 published |
| `acceptance_watch.py` | Task Scheduler | 6 h | `state\acceptance_latest.md`, `state\acceptance_history\` | any FAIL |
| `backup_state.py` | Task Scheduler | daily 02:00 | `logs\backup.log`, `d:\omniroute-backups\<date>\` | missing files |
| `db_integrity_watch.py` | Task Scheduler | daily 02:30 | `state\db_integrity_report.json` | WAL > 8 MB / corrupt |
| `purge_dead_connections.py` | Task Scheduler | daily 03:00 | `state\purge_report.json` | unsupported delete path |
| `wire_openrouter_fallback.py` | Task Scheduler | daily 03:30 | `state\openrouter_fallback_report.json` | update failures |
| `deactivate_zai_combo.py` | Task Scheduler | daily 03:45 | `state\zai_deactivation_report.json` | update failures |
| `coverage_report.py --apply` | Task Scheduler | daily 04:00 | `state\coverage_report.json`, `logs\coverage_report.md` | coverage drop / new harvestable |
| `residual_latency_probe.py` | Task Scheduler | 6 h | `state\residual_latency_report.json` | >1 stall / 5s+ in a pass |

Registration commands are in `docs/INSTALLATION.md` §8.

---

## 2. Scheduled tasks (Task Scheduler names)

| Task name | Script | Purpose |
|---|---|---|
| `OmniRoute OAuth KeepAlive` | `oauth_keepalive_task.bat` | refresh OAuth tokens before expiry |
| `OmniRoute HealthWatch` | `health_watch_task.bat` | detect failing connections |
| `OmniRoute StallMonitor` | `stall_monitor_task.bat` | detect event-loop freezes |
| `OmniRoute ReleaseWatch` | `release_watch_task.bat` | alert when v3.8.50 ships |
| `OmniRoute AcceptanceWatch` | `acceptance_watch_task.bat` | regression detection |
| `OmniRoute DailyBackup` | `backup_state_task.bat` | nightly state backup |
| `OmniRoute DbIntegrity` | `db_integrity_watch_task.bat` | read-only WAL/integrity check |
| `OmniRoute PurgeDead` | `purge_dead_connections_task.bat` | purge dead connections (supported API) |
| `OmniRoute WireFallback` | `wire_openrouter_fallback_task.bat` | OpenRouter weight-0 fallback entries |
| `OmniRoute DeactivateZai` | `deactivate_zai_combo_task.bat` | deactivate dead auto/zai combo |
| `OmniRoute CoverageReport` | `coverage_report_task.bat` | 295-provider coverage + worklist |
| `OmniRoute ResidualLatency` | `residual_latency_probe_task.bat` | P4 latency characterization |

Verify registration:

```powershell
schtasks /query /tn "OmniRoute OAuth KeepAlive"
```

Force a run:

```powershell
schtasks /run /tn "OmniRoute HealthWatch"
```

---

## 3. Known residual issue — blocker #3 (catalog rebuild freeze)

**Symptom:** one `/v1/models` request every ~10.6 min takes 24–38 s (all other
requests ~2 s). Cause: synchronous model-catalog rebuild after the 60s/600000ms
TTL expires (worklog #22–#25, #31–#32). **Fixed upstream in unreleased v3.8.50**
(PRs #8728 SWR, #8987 memoization, #9199 responsiveness).

**On 3.8.49, mitigations in place:**
1. `modelCatalogCacheTtlMs=600000` (10 min TTL) → rebuild cadence reduced ~6.4×
   (worklog #32, still the single most effective mitigation).
2. Optional: Caddy SWR proxy in front of `:20128` at `:20230`
   (`config/caddy/Caddyfile`, Fix P3) — serves cached catalog during freezes.
3. `stall_monitor.py` watches for it so you always know when it happens.

**Do not** raise the TTL further (schema clamps at 600000 and the invalidation
gap documented in worklog #25 makes a longer TTL unsafe).

---

## 4. Upgrade to v3.8.50 (when released)

**Trigger:** `state/release_watch.json` shows `newer_than_baseline: true`
(i.e. `npm view omniroute dist-tags` shows latest ≥ 3.8.50).

**Pre-upgrade (all verified green before touching anything):**
```powershell
python d:\omniroute-monetizer\acceptance_tests.py     # must be MONETIZER_READY
d:\omniroute-monetizer\.venv\Scripts\python.exe d:\omniroute-monetizer\scripts\automation\backup_state.py
# confirm the two disable flags are still in .env / NSSM AppEnvironmentExtra
```

**Upgrade:**
```powershell
cd C:\Users\Admin\AppData\Local\hermes\node\node_modules
npm install omniroute@latest --ignore-scripts
```

**Bounce (user-run, elevated — non-admin cannot stop the LocalSystem service):**
```powershell
nssm restart OmniRoute        # or: Restart-Service OmniRoute (elevated)
```

**Post-upgrade:**
1. Check `service-stderr.log` banner — if the two flags are still set, the
   sweepers stay off. Evaluate whether to **re-enable** them now that upstream
   fixed the unfiltered sweep (#9180) — the choice is yours; the flags are the
   safe default on 3.8.49.
2. `4x GET /v1/models` latency probe → all ~2 s, no 37 s stall.
3. Full acceptance run (`acceptance_tests.py`) → expect `MONETIZER_READY`.
4. `stall_monitor.py` for 15 min → clean (no more periodic freezes).

> After upgrade, the TTL setting may persist (it is stored in the DB settings
> store). Re-verify with `GET /api/settings/cache-config`. The 600000 value
> remains safe.

**Decision already made (worklog #25):** do **not** patch 3.8.49's minified
webpack chunks — the invalidation gap makes any TTL hotfix unsafe, and SWR
cannot be backported cleanly.

---

## 5. Restore procedure (from backup)

1. Stop the service (user-run, elevated):
   ```powershell
   nssm stop OmniRoute
   ```
2. Restore files from the latest `d:\omniroute-backups\<date>\`:
   - `storage.sqlite` (+ `-wal`/`-shm` if present) → `C:\Users\Admin\.omniroute\`
   - `state/*` → `d:\omniroute-monetizer\state\`
3. Start the service:
   ```powershell
   nssm start OmniRoute
   ```
4. Verify: acceptance suite + health check (see §0).

---

## 6. Credential / secret hygiene (T11)

- **Never** hardcode secrets in scripts; resolve via the DPAPI vault
  (`state\omniroute_password.bin`, machine-scoped — worklog #47) or env vars.
- `state/generated_keys.json`, `state/omniroute_password.bin`,
  `state/browser_profile/` are **gitignored** and backed up only to the local
  backup dir.
- If a key ever appears in git history, treat it as **burned**: rotate at the
  provider, then purge history (see `scratch/audit_git_history.py` /
  `state/git_secret_audit.json`).

---

## 7. OAuth provider status (what to expect)

| Provider | Mechanism | Auto-refresh? | Notes |
|---|---|---|---|
| amazon-q, kimi-coding, codex, kiro | native `/refresh` | ✅ every 15 min | expiresAt advances +1 h |
| github, kilocode | self-managed token | ✅ | refresh returns "no new token"; still healthy |
| trae, windsurf ×2 | OAuth (dead) | ❌ | require one-time re-login (human-in-loop, worklog #36) |
| anthropic | billing-walled | ⏸ | key stored; inject once credits added (worklog #35) |

---

## 8. Manual operations that require a human

| Operation | Why | How |
|---|---|---|
| NSSM bounce (restart service) | non-admin cannot stop LocalSystem service | `nssm restart OmniRoute` from an elevated prompt |
| OAuth re-login (trae/windsurf) | expired sessions need interactive login | reuse `scratch/export_sessions_cdp.py` pattern |
| Anthropic billing | free plan, no credits | purchase credits → inject stored key via one `PUT /api/providers/{id}` |
| Git-history secret purge | G9 | rotate first, then `git filter-repo` + force-push (user decision) |

---

## 9. Escalation ladder

1. Single provider failure → check `health_log.json`; re-run `health_watch.py`;
   usually self-healing (keep-alive rotates OAuth tokens).
2. Repeated `/v1/models` stalls → confirm with `stall_monitor.py`; it is blocker
   #3 (expected on 3.8.49); consider enabling the Caddy SWR proxy.
3. Service crash-loop / watchdog exit → read `service-stderr.log`; if
   `[Encryption] Auth tag validation` appears, follow the WAL-recovery procedure
   (worklog #14–#18) — backup DB, delete `-wal`/`-shm`, bounce.
4. Everything else → open the worklog, find the matching entry, and document the
   new finding before touching anything (AGENTS.md discipline).
