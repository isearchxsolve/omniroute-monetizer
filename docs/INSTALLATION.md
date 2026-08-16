# OmniRoute Monetizer — Reproducible Installation Guide

> **Status:** operational procedure derived from the sandbox install (worklog #31)
> and the live deployment (worklog #14, #21, #22). This is the exact sequence that
> produced a working OmniRoute v3.8.49 with the two health-sweep disables and the
> 10-minute catalog TTL.
>
> **Ground rules (AGENTS.md):** no DB hacking (REST APIs only); no fabricated
> credentials (upstream 200 OK required); sandbox-first for risky changes; secrets
> never committed (T11).

---

## 1. Prerequisites

| Item | Version | Notes |
|---|---|---|
| Node.js | v22.23.2 (observed) | `node -v` |
| npm | bundled with Node | `npm -v` |
| OS | Windows (service via NSSM) | Linux dev-sandbox is also supported for testing |
| Python | 3.11 (automation venv) | `scripts/requirements-browser.txt` |
| Free disk | ~2 GB | `node_modules` ~1 GB + data |

---

## 2. Install OmniRoute 3.8.49

```powershell
# Create install dir and install with --ignore-scripts (sandbox-proven; scripts
# are not needed and would try to run native post-install steps).
mkdir C:\Users\Admin\AppData\Local\hermes\node\node_modules
cd C:\Users\Admin\AppData\Local\hermes\node\node_modules
npm install omniroute@3.8.49 --ignore-scripts
```

> **Pin exactly 3.8.49.** Do not take `@latest` unless you have read
> `docs/OPS_RUNBOOK.md` §Upgrade (the blocker-#3 SWR fix lands in v3.8.50, which
> is currently **unreleased**; `npm view omniroute dist-tags` confirms only
> `3.8.49` is published).

---

## 3. Environment file (`.env`)

Create `C:\Users\Admin\.omniroute\.env` (or the install dir's `.env` — the
service reads it on a fresh start via `loadEnvFile()`; see worklog #21).

```dotenv
# --- service identity ---
PORT=20128
HOST=0.0.0.0

# --- data ---
DATA_DIR=C:\Users\Admin\.omniroute

# --- bootstrap admin password (used once at first login) ---
INITIAL_PASSWORD=<GENERATE-A-STRONG-VALUE>

# --- database encryption key: 64 hex chars, generate fresh ---
STORAGE_ENCRYPTION_KEY=<64-HEX-CHARS>

# --- WebSocket ports (offset to avoid collisions with other services) ---
WS_PORT=20231
WS_PORT_ALT=20232

# --- CRITICAL: disable the two event-loop-blocking health sweepers on 3.8.49 ---
# vendor bug #1: CredentialHealth sweep tested ALL 51 connections unfiltered
# vendor design flaw #2: token health-check refresh-tests ALL dead OAuth tokens
# both blocked the single-threaded event loop ~37s per ~100s (worklog #21-#22).
OMNIROUTE_DISABLE_CREDENTIAL_HEALTH_CHECK=true
OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK=true
```

Generate the secrets:

```powershell
# 64 hex chars
-join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })

# strong password
$rand = [System.Security.Cryptography.RandomNumberGenerator]::Create()
# ... use your preferred generator ...
```

> **Never commit this file.** It is covered by `.gitignore` (`*.env`).

---

## 4. Start OmniRoute once (bootstrap)

```powershell
cd C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute
node bin\omniroute.mjs
```

Wait for the banner (`✓ Ready in ...`, `[DB] SQLite database ready`) then log in
once at `http://localhost:20128` with the `INITIAL_PASSWORD` value. After first
login, change the password and store it in the DPAPI vault:

```powershell
python scripts\automation\password_vault.py --store
```

---

## 5. Register as a Windows service (NSSM)

```powershell
# Locate nssm (e.g. via winget):
winget install NSSM.NSSM

nssm install OmniRoute "C:\Users\Admin\AppData\Local\hermes\node\node.exe"
nssm set OmniRoute AppDirectory "C:\Users\Admin\AppData\Local\hermes\node\node_modules\omniroute"
nssm set OmniRoute AppParameters "--max-old-space-size=4096 bin\omniroute.mjs"
nssm set OmniRoute AppEnvironmentExtra "PORT=20128" "DATA_DIR=C:\Users\Admin\.omniroute" "STORAGE_ENCRYPTION_KEY=<64-HEX-CHARS>" "OMNIROUTE_DISABLE_CREDENTIAL_HEALTH_CHECK=true" "OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK=true"
nssm set OmniRoute AppExit Default Restart
nssm set OmniRoute AppRestartDelay 10000
nssm set OmniRoute AppThrottle 30000
nssm start OmniRoute
```

> **Important (worklog #21 §G):** a child-only restart (`POST /api/restart`)
> respawns with the supervisor's **stale env snapshot** and will MISS `.env`
> changes. The two disable flags only take effect after a **full NSSM service
> bounce**. Always bounce via `nssm restart OmniRoute` (needs elevation).

---

## 6. Post-install configuration

1. **Restore cache settings** (if you have a prior `cache-config` backup):

   ```powershell
   python scripts\automation\omniroute_api.py --apply-cache-config state\live_cache_config_backup_*.json
   ```

2. **Raise the model-catalog TTL** (blocker #3 mitigation, worklog #32) — the
   runtime honors the raw DB value per-request, no restart needed:

   ```
   PUT /api/settings/cache-config   {"modelCatalogCacheTtlMs": 600000}
   ```

   (Backup first via `GET /api/settings/cache-config`.)

3. **Restore provider connections**: import from your backup (Fix G10) or
   re-add each provider via `scripts/automation/omniroute_api.py`.

4. **Verify**:

   ```powershell
   python acceptance_tests.py
   # Expect: [PASS] MONETIZER_READY — All 20 tests passed
   ```

---

## 7. Python automation venv

```powershell
cd d:\omniroute-monetizer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r scripts\requirements-browser.txt
```

Required runtime deps: `requests`, `playwright` (browser automation only),
`psutil` (optional monitoring).

---

## 8. Scheduled tasks (all production monitors)

Run these **once** from an elevated prompt (worklog #36 pattern):

```powershell
schtasks /create /tn "OmniRoute OAuth KeepAlive" /tr "d:\omniroute-monetizer\scripts\automation\oauth_keepalive_task.bat" /sc minute /mo 15
schtasks /create /tn "OmniRoute HealthWatch"    /tr "d:\omniroute-monetizer\scripts\automation\health_watch_task.bat"     /sc minute /mo 15
schtasks /create /tn "OmniRoute StallMonitor"   /tr "d:\omniroute-monetizer\scripts\automation\stall_monitor_task.bat"    /sc minute /mo 15
schtasks /create /tn "OmniRoute ReleaseWatch"   /tr "d:\omniroute-monetizer\scripts\automation\release_watch_task.bat"    /sc minute /mo 30
schtasks /create /tn "OmniRoute AcceptanceWatch" /tr "d:\omniroute-monetizer\scripts\automation\acceptance_watch_task.bat" /sc hour /mo 6
schtasks /create /tn "OmniRoute DailyBackup"    /tr "d:\omniroute-monetizer\scripts\automation\backup_state_task.bat"     /sc daily /st 02:00
```

---

## 9. Sandbox reproduction (optional, for safe testing)

```powershell
mkdir d:\omniroute-sandbox
cd d:\omniroute-sandbox
npm install omniroute@3.8.49 --ignore-scripts
# .env with PORT=20199, DATA_DIR=d:\omniroute-sandbox\data, WS_PORT=20231/20232
node node_modules\omniroute\bin\omniroute.mjs
```

---

## 10. Verification checklist

| Check | Command | Expected |
|---|---|---|
| Service up | `curl -s -o /dev/null -w "%{http_code}" http://localhost:20128/` | `200` |
| Models | `curl -s http://localhost:20128/v1/models` | JSON `data` array |
| Auth | `curl -s -o /dev/null -w "%{http_code}" http://localhost:20128/api/providers` | `401` |
| Acceptance | `python acceptance_tests.py` | `MONETIZER_READY` |
| No sweepers | check `service-stderr.log` | no `[HealthCheck]`/`[CredentialHealth]` banners |
| TTL | `GET /api/settings/cache-config` | `modelCatalogCacheTtlMs: 600000` |
