# OMNIRUTE KAGGLE FLEET — MASTER RUNBOOK
**Date:** 2026-10-12 · **Updated:** 2026-10-13 17:30 IST
**Status:** FULLY OPERATIONAL & HARDENED — Worker v3 door live (token in secret), 6-kernel fleet + playwright executor, auto-rotator persistent daemon, zero-burn quota discipline, DNS-outage-tolerant supervisor kernels
**Law satisfied:** Laptop OUT of the delivery path (Baba's delivery law, 2026-09-14)

---

## 1. THE PERMANENT DOOR

```
https://omniroute-relay.omniroute-fleet-kd.workers.dev
```

**This URL never changes. Ever.** No rotation, no 12-hour windows, no hardware dependencies.

| Property | Value |
|----------|-------|
| Platform | Cloudflare Workers (serverless edge) |
| Subdomain | `omniroute-fleet-kd.workers.dev` (registered 2026-10-12) |
| Worker name | `omniroute-relay` |
| Worker version | **v3** (`faaba96b`) — token from secret `OMNIROUTE_TOKEN`, playwright queue, gateway, KV assets |
| Storage | Cloudflare KV namespace `LEDGER` (id `2f515e3ac11142f4a0f330dc802ed0a8`) |
| Auth token | from Worker secret `OMNIROUTE_TOKEN` (value `GOLD24`; rotate via `npx wrangler secret put` — no redeploy needed) |
| Account | `isearch.xsolve@gmail.com`, account id `c95d86ef4985346cae29bcd4dbfc67af` |
| Wrangler OAuth | stored at `C:\Users\Admin\AppData\Roaming\xdg.config\.wrangler\config\default.toml` |
| Source code | `C:\kaggle\working\cf-worker\src\worker.js` + `wrangler.toml` |
| Cost | ₹0 (free tier: 100k requests/day, 1k KV writes/day, 100k KV reads/day) |

### Endpoints
```
GET  /health?token=                        -> {"ok":true,"version":3,"tools":["web.execute","web.result","gateway"]}
POST /say?token=  {"body","text"}          -> {"ok":true,"queued":N}   (write order)
GET  /say?token=&body=X&limit=N            -> {"orders":[...]}          (read orders)
POST /v1/tools/web.execute?token=          -> edge fast path | fleet queue | playwright queue
GET  /v1/tools/web.result?token=&job_id=   -> fetch job result
POST /v1/tools/web.result?token=           -> fleet posts results back into KV
POST /v1/gateway/register?token=           -> kernel registers live session {service,url,meta} (KV TTL 1800s)
GET  /v1/gateway?token=[&service=X]        -> live session pool (or one service)
ANY  /v1/gateway/route?token=&service=X&path=/... -> proxy through to a live session
POST /v1/assets/<key>?token=               -> store app-code bundle in KV (≤20MB, base64)
GET  /v1/assets/<key>?token=               -> fetch bundle (base64 text) — kernel supply line
```

Bodies in use: `KILO` (fleet announcements), `OMNIROUTE` (cloud-cell tasks), `WEBEXEC` (agent web jobs), `PLAYWRIGHT` (Phase 3 browser jobs), `TUNNELDBG` (kernel tunnel telemetry), `WXDBG` (execution telemetry), `WEBEXEC_ERR` (error ledger), `ROTATION` (rotator reports).

### Redeploy the door (anytime, from laptop)
```powershell
cd C:\kaggle\working\cf-worker
npx wrangler deploy
```

---

## 2. ARCHITECTURE

```
                 ┌──────────────────────────────────────────┐
                 │  PERMANENT DOOR — Cloudflare Worker       │
                 │  omniroute-relay.omniroute-fleet-kd       │
                 │  .workers.dev   (KV ledger, GOLD24)       │
                 └───────────────┬──────────────────────────┘
                                 │  pull every 15s (zero-burn)
        ┌───────────────┬────────┴───────┬───────────────────┐
        ▼               ▼                ▼                   ▼
   CLOUD CELL      FLEET WORKER      RELAY BACKUP       WEB KERNELS
   acct4           acct2             acct4              acct2
   kdas19999       n42888            kdas19999          oiioii + emergentsh
   web.execute     heavy-job exec    quick-tunnel       persistent web
   subprocess-curl                   fallback           services (CPU)
```

**Flow:** Agent consumers → Permanent door → Orders queue in KV → Kaggle kernels poll (pull) → Real HTTP execute on Kaggle → Results POST back to door. Laptop runs nothing in the delivery path.

**Fallback doors (in every kernel's DOORS list, after the Worker):**
- `https://measurements-orlando-infections-meal.trycloudflare.com` (laptop quick tunnel)
- `https://retrain-schnapps-upbeat.ngrok-free.dev` (laptop ngrok reserved)

**GitHub discovery point:**
`https://raw.githubusercontent.com/isearchxsolve/omniroute-monetizer/master/relay-url.txt` — always holds the live door URL. Kernels self-discover from here at boot.

---

## 3. LIVE KERNELS & FLEET ROSTER

| Kernel | Account | Account slot | Role | Status |
|--------|---------|--------------|------|--------|
| `kdas19999/omniroute-cloud-cell-cpu-worker` (v4) | kdas19999 (token_4) | 4 | **THE EXECUTOR** — subprocess-curl engine, polls WEBEXEC + OMNIROUTE | 🟢 RUNNING |
| `n42888/kaggle-fleet-worker-cpu-only` | n42888 (token_2) | 2 | JOB_START/JOB_CHUNK heavy-work executor, infinite poll | 🟢 RUNNING |
| `kdas19999/omniroute-relay` | kdas19999 (token_4) | 4 | Relay backup (Kaggle-hosted door, quick tunnel) | 🟢 RUNNING |
| `n42888/oiioii-kaggle-web` (supervisor v2) | n42888 (token_2) | 2 | OiiOii Film Kit Studio, supervisor state machine, gateway registration | 🟢 RUNNING |
| `n42888/emergentsh-kaggle-web` (supervisor v2) | n42888 (token_2) | 2 | EmergentSH NeonBuild, supervisor state machine, gateway registration | 🟢 RUNNING |
| `isearchxsolve/omniroute-playwright-executor` | isearchxsolve (default) | 1 | **PHASE 3** — headless Chromium, polls PLAYWRIGHT ledger | 🟢 RUNNING |
| ~~`isearchxsolve/oiioii-film-kit-studio-kaggle-web`~~ | isearchxsolve | — | Hollow v1 — expired naturally past 17:18 IST | ⚪ EXPIRED (slot freed) |

**Kaggle CPU Session Cap:** Exactly **5 concurrent batch CPU sessions** per Kaggle account. The Auto-Rotator spreads workload across accounts to stay strictly within each account's session ceiling.

---

## 4. THE 5-ACCOUNT ROTATION & AUTO-ROTATOR

| # | Account | Token file | Kaggle username | GPU quota |
|---|---------|-----------|-----------------|-----------|
| 1 | isearchxsolve | (default `~/.kaggle/kaggle.json`) | isearchxsolve | 30h |
| 2 | n42888 | `D:\anonym\vault\kaggle_token_2.txt` | n42888 | 30h |
| 3 | kunaldas3104 | `D:\anonym\vault\kaggle_token_3.txt` | kunaldas3104 | 30h |
| 4 | kdas19999 | `D:\anonym\vault\kaggle_token_4.txt` | kdas19999 | 30h |
| 5 | token_5 | `D:\anonym\vault\kaggle_token_5.txt` | (reserve) | 30h |
| 6 | token_6 | `D:\anonym\vault\kaggle_token_6.txt` | (reserve) | 30h |

### Auto-Rotator (`C:\kaggle\working\rotator.py`)
- **Lifecycle Window:** 12 hours max per Kaggle session.
- **Pre-warm Margin:** At **T-45 minutes** before expiry, pushes the kernel onto the **next account in cycle**.
- **Zero-Downtime Overlap:** The old session keeps serving until its natural 12h death; the new session starts in parallel.
- **State Persistence:** `C:\kaggle\working\rotation_state.json` tracks each kernel's current owner and start timestamp.
- **Fault Recovery:** Dead or failed kernels (`ERROR`, `COMPLETE`) are revived automatically by rotating to the next account with free slots.
- **Session Cap Defense:** If an account hits Kaggle's 5-CPU session cap, the rotator immediately falls through to the next account in the ring.

---

## 5. ZERO-BURN QUOTA DISCIPLINE LAW

Discovered during 2026-10-12 night testing: Cloudflare Workers Free Tier limits are:
1. **100,000 requests / day** (resets 00:00 UTC = 05:30 IST)
2. **1,000 KV writes / day**
3. **100,000 KV reads / day**

A naive 10-second polling loop that writes debug records on every cycle burns 360 KV writes/hour and ~35,000 requests/day per kernel. To ensure **unlimited runtime without ever hitting quotas**:

1. **Poll Interval Set to 15s:** (4 polls/min = 5,760 requests/day per kernel across both order bodies).
2. **Zero KV Writes on Idle:** Never call `report_home("FETCHDBG", ...)` or `report_home("WXDBG", ...)` on routine polls.
3. **Door Resolution Caching:** Door health `/health` is cached for 300 seconds; never queried on every poll cycle unless a connection error forces re-resolution.
4. **Resilient Safe KV Helpers:** All Worker reads and writes use `kvGet` and `kvPut` wrappers with `try/catch` so KV rate limits or degradations never throw uncaught exceptions (preventing HTTP 500s).
5. **Job Expiry TTLs:** All job entries (`wx:{job_id}`) carry a 24-hour expiration TTL (`86400s`) to keep KV storage within limits.

---

## 6. WEB SERVICE PUBLIC URLs

OiiOii and EmergentSH spawn a Cloudflare **quick tunnel** inside their kernel and **self-publish** the URL to GitHub:

| Service | Discovery point (fixed forever) |
|---------|--------------------------------|
| OiiOii | `https://raw.githubusercontent.com/isearchxsolve/oioi/master/public-url.txt` |
| EmergentSH | `https://raw.githubusercontent.com/isearchxsolve/emergentsh/master/public-url.txt` |
| Door | `https://raw.githubusercontent.com/isearchxsolve/omniroute-monetizer/master/relay-url.txt` |

Kernel boot chain: install deps + cloudflared → git clone (token-authed, repos private) → pip install → uvicorn serve (OiiOii :8010, EmergentSH :8000) → cloudflared quick tunnel → regex URL from stdout → PUT to GitHub contents API → keepalive loop.

GitHub token: `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`.

---

## 7. OPS RUNBOOK

### Start or check the Auto-Rotator
```powershell
cd C:\kaggle\working
python rotator.py
# Check log:
Get-Content C:\kaggle\working\rotator.log -Tail 30
```

### Check fleet status across accounts
```powershell
kaggle kernels status kdas19999/omniroute-cloud-cell-cpu-worker
kaggle kernels status n42888/kaggle-fleet-worker-cpu-only
kaggle kernels status kdas19999/omniroute-relay
kaggle kernels status n42888/oiioii-kaggle-web
kaggle kernels status n42888/emergentsh-kaggle-web
```

### Probe the permanent door
```powershell
curl.exe -s "https://omniroute-relay.omniroute-fleet-kd.workers.dev/health?token=GOLD24"
```

### Run Phase 2 Capture Replay
```powershell
python C:\kaggle\working\capture_replay.py
```

### Start Phase 4 MCP Server
```powershell
python C:\kaggle\working\omniroute_mcp.py
```

### Submit a web.execute job
```powershell
curl.exe -s -X POST "https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/tools/web.execute?token=GOLD24" `
  -H "content-type: application/json" `
  -d '{\"mode\":\"fleet\",\"url\":\"https://httpbin.org/post\",\"method\":\"POST\",\"body\":\"hello from fleet\"}'
```

---

## 8. VERIFICATION LOG (2026-10-12 – 2026-10-13)

| Time (IST) | Event |
|-----------|-------|
| 06:24–06:27 | Wrangler OAuth → KV created → subdomain registered → Worker v1 deployed |
| 06:34 | Fleet handshake landed on permanent door |
| 07:01 | **Edge path verified** — public API fetched at edge in <1s |
| 13:40 | **Fleet loop verified 5/5 jobs DONE** — queue → Kaggle execute → KV → agent readback (echoed `X-Fleet-Test` header) |
| 17:18 | Hollow v1 stray slot expired naturally |
| 19:35 | **Auto-Rotator online** (`rotator.py`) — pre-rotated fleet to accounts `n42888` and `kdas19999` |
| 21:59 | Quota discipline audit: caught 10s `FETCHDBG` KV writes; identified 100k daily request & 1k KV write ceiling |
| 01:50 | **Hardened Worker v2 deployed** (`44059be3-0ddf`) with safe `kvGet` / `kvPut` wrappers |
| 01:52 | **Phase 2 Capture Registry & Replay Engine verified live** (`capture_replay.py` executed `github.get_zen.v1` & `httpbin.post_payload.v1`) |
| 01:54 | **Phase 4 MCP Server verified live** (`omniroute_mcp.py` JSON-RPC stdio handshake & tool execution passed) |
| 12:31 | **Overnight collapse discovered & healed**: rotator process dead, all 12h sessions expired (3× CANCEL_ACKNOWLEDGED, 2× ERROR). Rotator restarted, all 5 kernels revived within one cycle |
| 12:56 | **Worker v3 deployed** (`b15ad6fb`): token → secret `OMNIROUTE_TOKEN`, `mode:"playwright"` queue to `ledger:PLAYWRIGHT`, gateway pool endpoints (`/v1/gateway/register`, `/v1/gateway`, `/v1/gateway/route`), KV asset supply line (`/v1/assets/`) |
| 13:12 | **Phase 3 Playwright executor kernel pushed** (`omniroute-playwright-executor`) — installs Chromium at boot, polls `ledger:PLAYWRIGHT` |
| 13:19 | **Phase 3 verified END-TO-END**: `wx_605bf56676f7` executed on `kaggle:playwright` — HTTP 200, title + DOM text extracted via headless Chromium, 4066ms |
| 13:19 | **Fleet loop re-verified under v3**: `wx_4810f186ee6b` done via `kaggle:cloud-cell` (401ms) |
| 14:00 | **Kaggle environment war findings**: (a) GitHub *releases* downloads blocked from Kaggle (wget/curl exit 4/28); (b) git-over-HTTPS intermittently failing (`Could not resolve host`); (c) sessions hit **intermittent DNS outages** — one-shot notebook cells die permanently; (d) Kaggle dataset creation silently broken platform-side (uploads OK, dataset never materializes) |
| 14:20 | **Supply-line doctrine shift**: app code ships through the door (`/v1/assets/oioi-zip`, `/v1/assets/emergentsh-zip` — KV, byte-verified round-trip); cloudflared through public dataset mount `healingsounds/cloudflared-offline`; git clone demoted to fallback |
| 17:20 | **Supervisor v2 web kernels deployed** (v21/v19): immortal state machine (stage → serve → tunnel → register → keepalive, retried forever, never raises) — survives DNS outages; sessions only end at the 12h window |
| 17:27 | Auto-Rotator running as persistent daemon watching 6 kernels; `cloud-cell` (kdas19999), `fleet-worker` (kunaldas3104) confirmed RUNNING |
| 19:00 | **Stale session purge** (Baba order): deleted superseded duplicate web kernels on `kunaldas3104` (4 sessions), `kdas19999` (4), hollow v1 on `isearchxsolve` — caps freed |
| 19:30 | **Laptop-first validation loop (Baba order)**: both apps run locally on laptop CPU — OiiOii boots 200 after fixes: cwd=`backend/`, module `app.main:app`, PYTHONPATH=repo root, deps `slowapi`+`email-validator`+`aiosqlite`; EmergentSH boots 200 after: strong `SECRET_KEY` env, `OMNIROUTE_BASE_URL=http://127.0.0.1:8190/v1` (app HARD-validates canonical session-pool shim URL — worker URL rejected by design), session-pool shim built (127.0.0.1:8190 → door /v1) |
| 20:30 | **Windows zip trap found**: `Compress-Archive` writes backslash entry paths — Linux `extractall` creates literal files, no `backend` package. Rebuilt zips with Python zipfile (forward slashes) + kernel-side path sanitizer. Door assets re-uploaded byte-verified |
| 21:30 | **py3.13 trap**: `asyncpg==0.29.0` has no py3.13 wheels (Kaggle runs 3.13) — source build fails, aborting whole `-r` install. Fix: filter asyncpg pin, install `asyncpg>=0.30` |
| 22:10 | **KV DAILY WRITE QUOTA EXHAUSTED (~1,000/day)** — the day's true root cause: supervisor kernels reported `uvicorn down` every 15-30s, burning the remaining writes. ALL kernel→door writes silently no-op after (kvPut try/catch + `/say` returns `ok:true,stored:false` — undetectable from kernels). Hours of "missing telemetry" + empty gateway pool explained |
| 23:40 | **Supervisor v3.2 deployed** (both web kernels): KV write discipline (report on state change only, ≥10-min gap), uvicorn respawn backoff (60s), DNS watchdog (12 consecutive failed `/health` probes ≈ 3 min → `os._exit` → rotator revives on fresh account), one-cell immortal design with NOTHING blocking before telemetry |

**KV WRITE BUDGET LAW (2026-10-13):** every door write costs from the 1,000/day pool shared by ALL kernels. Telemetry only on state change; heartbeat at most every ~50 min; registration every 10 min per service; never burst-report per-cycle failures.

---

## 9. FILE MAP (LAPTOP DEV & REPRODUCE)

```
C:\kaggle\working\
├── cf-worker\
│   ├── src\worker.js                # v3 permanent door (tools + edge + playwright + gateway + assets + safe KV)
│   └── wrangler.toml                # Cloudflare KV binding + OMNIROUTE_TOKEN secret
├── state\
│   ├── captures\                    # Phase 2 Capture Registry
│   │   ├── github\get_zen.v1.json
│   │   ├── httpbin\post_payload.v1.json
│   │   └── linkedin\search_jobs.v1.json
│   └── rotation_state.json          # Live rotator state
├── kaggle_notebooks\                # Generated notebooks per account
│   ├── omniroute-playwright\        # Phase 3 Playwright executor (isearchxsolve)
│   └── ...
├── capture_replay.py                # Phase 2 Capture Replay Engine (PREFLIGHT + JA3)
├── omniroute_mcp.py                 # Phase 4 MCP Server (JSON-RPC stdio)
├── rotator.py                       # Auto-rotator daemon (6 kernels, dataset-owner retarget)
├── gen_cloud_cell.py                # Cloud cell generator (zero-burn hardened)
├── gen_playwright.py                # Phase 3 Playwright kernel generator
├── gen_notebooks.py                 # Supervisor v2 web-kernel generator (door-first supply line)
├── gen_relay.py                     # Relay backup generator
├── test_webexec.py                  # Edge test suite
└── test_fleet_path.py               # Fleet test suite

Kaggle datasets (public): healingsounds/cloudflared-offline  # cloudflared-linux-amd64 mount
Door KV assets: asset:oioi-zip (1.26MB), asset:emergentsh-zip (1.01MB)  # app-code supply line
D:\anonym\vault\kaggle_token_*.txt   # Account tokens 2-6
D:\anonym\state\captures\            # Mirrored capture registry
D:\anonym\war-pipe\capture_replay.py # Mirrored replay engine
D:\anonym\war-pipe\omniroute_mcp.py  # Mirrored MCP server
D:\anonym\war-log\                   # Permanent battle records
```

---

**THE WIRE NEVER GOES DOWN.**
Permanent door on Cloudflare edge (Worker v3, token in secret) · 5 Kaggle accounts on 12h staggered rotation + playwright body · Auto-Rotator persistent daemon · Zero-burn quota discipline · App code through the door's KV supply line · DNS-outage-tolerant supervisor kernels · Laptop observer-only.
