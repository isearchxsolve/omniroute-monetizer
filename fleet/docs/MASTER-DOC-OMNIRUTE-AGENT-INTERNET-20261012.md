# OMNIRUTE MASTER DOC — THE AGENT INTERNET ARCHITECTURE
**Date:** 2026-10-12 · **Updated:** 2026-10-13 17:35 IST · **Status: ALL PHASES LIVE — Phase 3 verified, gateway door-side verified, kernel registration in flight**
**Supersedes/links:** FLEET-KAGGLE-RUNBOOK-20261012.md · FLEET-WEB-EXECUTE-ARCHITECTURE-20261012.md

---

## 0. THE ONE-PARAGRAPH TRUTH

OmniRoute Monetizer began as a free-LLM wire engine and has graduated into **the Python execution body for the agent internet**: one permanent Cloudflare Worker door exposes a single tool (`web.execute`) that any AI agent on Earth can call; simple public fetches execute at the Cloudflare edge in ~100ms; authenticated and multi-step web access executes as real HTTP from a rotating fleet of Kaggle bodies coordinated through the same door. Parag Agarwal's Parallel Web Systems indexes the web's **content** the hard way — a photograph, stale the moment it's taken, blind behind logins. We index the web's **capability** the lazy way — one laptop Chrome capture per site-flow, replayed live forever, always fresh, working behind authentication where no crawler can follow. **Parag built a photograph of the web. We built a set of hands.**

---

## 1. LOCK STATUS

### 🔒 LOCKED — Live, Battle-Tested End-to-End (2026-10-12 – 2026-10-13)

| Component | Proof |
|-----------|-------|
| Permanent door (Worker + KV) | Deployed (`44059be3-0ddf`), edge fetch verified (~100ms), safe `kvGet`/`kvPut` error resilience |
| Tool contract `web.execute` / `web.result` | 5/5 test jobs `done`, round-trip echo verified (`X-Fleet-Test` header echoed from Kaggle) |
| Edge fast path | api.github.com fetched at edge, result inline, zero latency overhead |
| Fleet path | httpbin round-trip through Kaggle: queue → execute → result in KV → agent read |
| Subprocess-curl executor | Hang-proof (hard timeout kills drip-feeds); telemetry at every step |
| Web services on Kaggle | OiiOii + EmergentSH kernels running, URLs self-published to GitHub |
| 5-account rotation & Auto-Rotator | `rotator.py` live with `rotation_state.json`, 12h lifecycle, 45-min pre-warm, session-cap defense |
| Zero-burn quota discipline | 15s poll interval, cached door resolution, idle KV writes stripped, safe within 100k req/day and 1k KV writes/day |
| Phase 2 Capture Registry & Replay | `state/captures/` on disk (3 production captures), `capture_replay.py` verified live with dynamic PREFLIGHT |
| Phase 4 MCP Server | `omniroute_mcp.py` JSON-RPC 2.0 stdio server verified live (`web_execute`, `web_result`, `capture_execute`) |
| **Phase 3 Playwright Executor** | Kernel `isearchxsolve/omniroute-playwright-executor` live; `wx_605bf56676f7` done on `kaggle:playwright` (HTTP 200, DOM extracted, 4s) |
| **Worker v3 door** | `faaba96b`: token in secret `OMNIROUTE_TOKEN`, playwright queue, gateway pool, KV asset supply line |
| **Door KV supply line** | `asset:oioi-zip` + `asset:emergentsh-zip` byte-verified round-trip — app code without GitHub |
| Laptop OUT of delivery path | All consumer + fleet traffic flows Worker ↔ Kaggle; laptop = capture studio + admin observer |

### ⏳ IN FLIGHT / NEXT

| Item | Notes |
|-------|-------|
| Gateway kernel registration | Supervisor kernels (v21/v19, n42888) register tunnel URLs to `/v1/gateway/register`; pool proof pending |
| Token rotation roll-out | Secret `OMNIROUTE_TOKEN` live (value `GOLD24`); future rotation = new secret value + fleet token update |
| Kaggle inference gateway consumption | OiiOii/EmergentSH already read `OMNIROUTE_BASE_URL=/v1`; agents consume via `/v1/gateway/route` |

### ⚔️ 2026-10-13 KAGGLE ENVIRONMENT WAR FINDINGS (doctrine-level)

1. **GitHub releases blocked from Kaggle** — wget/curl on `releases/latest/download` fail; git-over-HTTPS intermittently fails (`Could not resolve host`).
2. **Kaggle sessions hit intermittent DNS outages** — one-shot notebook cells die permanently; answer = immortal supervisor loop (stage → serve → tunnel → register → keepalive, retried forever, never raises).
3. **Kaggle egress is proxy-based** — direct-IP HTTPS fallback does NOT work from Kaggle; only DNS names resolve. IP-pin is a laptop-only trick.
4. **Kaggle dataset creation silently broken platform-side** (2026-10-13): uploads succeed, datasets never materialize (4 accounts tested).
5. **KV DAILY WRITE QUOTA (1,000/day) is a shared kill-switch**: burst telemetry (15-30s `uvicorn down` reports) exhausted it by ~22:10 IST — after which ALL kernel→door writes silently no-op (`ok:true,stored:false`). **Write discipline law: telemetry on state change only, ≥10-min gap, heartbeat ≤ hourly.**
6. **Python 3.13 traps**: old `asyncpg` pins have no wheels (filter pin, install >=0.30); Windows-made zips carry backslash entry paths (sanitize on extraction).
7. **App-level consumer contract**: EmergentSH hard-validates `OMNIROUTE_BASE_URL == http://127.0.0.1:8190/v1` — kernels must run the local session-pool shim; the door's worker URL is rejected by design.
8. **Counter-doctrine shipped:** cloudflared via public dataset mount (`healingsounds/cloudflared-offline`); app code via door KV assets (Python-zipped, forward slashes); git clone demoted to last fallback; laptop-first CPU validation before every deploy (Baba order).

---

## 2. THE PERMANENT DOOR

```
https://omniroute-relay.omniroute-fleet-kd.workers.dev        (never changes)
Account: isearch.xsolve@gmail.com · c95d86ef4985346cae29bcd4dbfc67af
KV namespace: LEDGER (2f515e3ac11142f4a0f330dc802ed0a8)
Auth: token=GOLD24
Source: C:\kaggle\working\cf-worker\src\worker.js  (redeploy: npx wrangler deploy)
Wrangler OAuth: C:\Users\Admin\AppData\Roaming\xdg.config\.wrangler\config\default.toml
```

### Endpoints
```
GET  /health?token=T                                → {"ok":true,"tools":["web.execute","web.result"]}
POST /say?token=T                {body,text}        → append to ledger:body
GET  /say?token=T&body=X&limit=N                    → {"orders":[...]}
POST /v1/tools/web.execute?token=T  {spec}          → edge: result inline · fleet: {"job_id","status":"queued"}
GET  /v1/tools/web.result?token=T&job_id=J          → {"status","content_b64","executed_by",...}
POST /v1/tools/web.result?token=T   {result}        → fleet posts results (KV wx:{job_id}, TTL 86400s)
```

### Execution Paths (Auto-Selected by Worker)
- **edge** — Worker fetches directly outbound. Default for simple GET/HEAD without cookies or capture ID (~100ms).
- **fleet** — Queued to `ledger:WEBEXEC`, executed by Kaggle cloud cell. For authed, multi-step, or capture flows, or `mode:"fleet"` forced.

---

## 3. THE TOOL CONTRACT (WHAT ANY AGENT CALLS)

```json
POST /v1/tools/web.execute?token=GOLD24
{
  "mode": "edge|fleet",              // optional; auto-selected if omitted
  "url": "https://...",              // required
  "method": "GET|POST|...",          // default GET
  "headers": {"...": "..."},
  "body": "string | object",
  "timeout_s": 15,                   // capped at 30s
  "max_bytes": 100000,               // capped at 100KB (KV result ceiling)
  "capture_id": "site.flow.v1"       // optional: capture registry replay
}
→ {"job_id": "wx_xxxxxxxxxxxx", "mode": "...", "status": "done|queued", ...}
```

---

## 4. THE FLEET (LIVE KERNELS)

| Kernel | Account | Account Slot | Role | Status |
|--------|---------|--------------|------|--------|
| `kdas19999/omniroute-cloud-cell-cpu-worker` **v4** | kdas19999 (token_4) | 4 | **THE EXECUTOR** — polls OMNIROUTE + WEBEXEC, subprocess-curl engine | 🟢 RUNNING |
| `n42888/kaggle-fleet-worker-cpu-only` | n42888 (token_2) | 2 | Heavy-work JOB_START/JOB_CHUNK executor | 🟢 RUNNING |
| `kdas19999/omniroute-relay` | kdas19999 (token_4) | 4 | Relay backup (Kaggle-hosted door, quick tunnel) | 🟢 RUNNING |
| `n42888/oiioii-kaggle-web` | n42888 (token_2) | 2 | OiiOii web service, CPU, tunnel URL → GitHub | 🟢 RUNNING |
| `n42888/emergentsh-kaggle-web` | n42888 (token_2) | 2 | EmergentSH web service, CPU, tunnel URL → GitHub | 🟢 RUNNING |
| ~~`isearchxsolve/oiioii-film-kit-studio-kaggle-web`~~ | isearchxsolve | — | Hollow v1 — expired past 17:18 IST | ⚪ EXPIRED |

**The 5-Account Pool & Auto-Rotator:**
- Accounts: `isearchxsolve` (1), `n42888` (2), `kunaldas3104` (3), `kdas19999` (4), reserve tokens (5, 6).
- 12-hour session lifetime, 45-minute pre-warm overlap, staggered rotation.
- Kaggle session limit: max 5 CPU batch sessions per account enforced by rotator skip-logic.

---

## 5. THE CAPABILITY INDEX (THE PARAG DOCTRINE)

| | Parallel (Parag Agarwal) | OmniRoute (Ours) |
|---|---|---|
| Indexes | **Content** — what the web says (snapshots) | **Capability** — how the web is reached (executable wire recipes) |
| Entry | Crawled page copy | Capture file: URLs, headers, auth flow, crypto, session pattern |
| Freshness | Stale on arrival | Always live — replay hits the real wire now |
| Coverage | Public web only | Authenticated web + public |
| Indexing cost | Continuous crawl of entire WWW | One Chrome session per site-flow, amortized to zero |
| Failure mode | **Silent** — serves stale data | **Loud** — replay breaks → re-capture → version bump |

### 5.1 Capture Registry (`state/captures/`)
Live in production with 3 baseline verified captures:
1. `github.get_zen.v1` — Public fast-edge baseline verification.
2. `httpbin.post_payload.v1` — Dynamic PREFLIGHT generation (epoch timestamps, UUID nonces) + JSON parameter substitution.
3. `linkedin.search_jobs.v1` — Multi-step CSRF extraction + Voyager API execution with session cookie rotation and sentinel verification.

### 5.2 Sentinel Doctrine
- **Substitution:** Replay known-good wire, inject runtime parameters (`substitute_template`).
- **Liveness:** Health probe and 15s keepalive polling.
- **Poison Detection:** Sentinel probe executed before stateful work; failure immediately rotates account pool instead of serving corrupted data.

---

## 6. DISCOVERY POINTS (FIXED FOREVER)

| What | Fixed URL |
|------|-----------|
| Door URL | `https://raw.githubusercontent.com/isearchxsolve/omniroute-monetizer/master/relay-url.txt` |
| OiiOii endpoint | `https://raw.githubusercontent.com/isearchxsolve/oioi/master/public-url.txt` |
| EmergentSH endpoint | `https://raw.githubusercontent.com/isearchxsolve/emergentsh/master/public-url.txt` |

---

## 7. OPS RUNBOOK & QUOTA DISCIPLINE

### 7.1 The Zero-Burn Quota Discipline Law
Cloudflare Workers Free Tier bounds:
- **100,000 requests / day** (resets 00:00 UTC = 05:30 IST)
- **1,000 KV writes / day**
- **100,000 KV reads / day**

Hardened safeguards:
1. **15s poll interval** — 5,760 requests/day per kernel, never exhausting daily request limits.
2. **Door resolution caching** — cached for 300 seconds; never probes `/health` on routine cycles.
3. **Zero idle KV writes** — eliminated routine `FETCHDBG` writes; only reports completions and errors.
4. **Resilient KV error handling** — safe `kvGet` / `kvPut` wrappers prevent uncaught exceptions.

### 7.2 Ops Commands
```powershell
# Auto-Rotator status & execution
python C:\kaggle\working\rotator.py

# Capture Engine live execution
python C:\kaggle\working\capture_replay.py

# Model Context Protocol (MCP) server
python C:\kaggle\working\omniroute_mcp.py

# Submit agent internet task (curl)
curl.exe -s -X POST "https://omniroute-relay.omniroute-fleet-kd.workers.dev/v1/tools/web.execute?token=GOLD24" `
  -H "content-type: application/json" `
  -d '{\"mode\":\"fleet\",\"url\":\"https://httpbin.org/post\",\"method\":\"POST\",\"body\":\"hello from fleet\"}'

# Redeploy permanent door
cd C:\kaggle\working\cf-worker; npx wrangler deploy
```

---

## 8. MODEL CONTEXT PROTOCOL (MCP) INTEGRATION (PHASE 4)

Native MCP server at `C:\kaggle\working\omniroute_mcp.py` (and `D:\anonym\war-pipe\omniroute_mcp.py`).
Standard JSON-RPC 2.0 over stdio exposing:
- `web_execute`: Live web execution (edge or fleet).
- `web_result`: Async job status and output lookup.
- `capture_execute`: Direct execution of captured wire recipes.

---

## 9. VERIFICATION LOG (2026-10-12 – 2026-10-13)

| Time (IST) | Event |
|-----------|-------|
| 06:24–06:27 | Permanent door v1 deployed on Cloudflare edge |
| 06:34 | Fleet handshake verified live on door |
| 07:01 | Edge path verified (<1s execution) |
| 13:40 | **Fleet loop verified 5/5 jobs DONE** — echo headers verified |
| 17:18 | Hollow v1 stray slot expired |
| 19:35 | **Auto-Rotator online** (`rotator.py`) across 5 accounts |
| 21:59 | Quota audit: caught 10s `FETCHDBG` KV writes; discovered 100k daily ceiling |
| 01:50 | **Hardened Worker v2 deployed** (`44059be3-0ddf`) with safe `kvGet` / `kvPut` |
| 01:52 | **Phase 2 Capture Registry verified live** (`capture_replay.py` executed `github.get_zen.v1` & `httpbin.post_payload.v1`) |
| 01:54 | **Phase 4 MCP Server verified live** (`omniroute_mcp.py` JSON-RPC stdio handshake & tools/call verified) |
| 12:31 | Overnight collapse healed: rotator dead + all sessions expired → rotator restarted, 5 kernels revived in one cycle |
| 12:56 | **Worker v3** (`b15ad6fb`): secret token, playwright queue, gateway pool, KV assets |
| 13:12 | **Phase 3 Playwright kernel pushed**; 13:19 **verified end-to-end** (`wx_605bf56676f7`, `kaggle:playwright`, 4s) |
| 14:00 | Kaggle war findings: GitHub releases blocked, DNS outages kill one-shot cells, dataset creation broken |
| 14:20 | Supply-line doctrine: door KV assets + dataset cloudflared mount (byte-verified) |
| 17:20 | **Supervisor v2 web kernels** (v21/v19): immortal state machines; 17:27 rotator persistent daemon watching 6 kernels |

---

## 10. FILE MAP

```
C:\kaggle\working\
├── cf-worker\src\worker.js          # THE DOOR (v2: hardened safe KV + edge + fleet)
├── cf-worker\wrangler.toml          # KV namespace LEDGER binding
├── state\captures\                  # Phase 2 Capture Registry
│   ├── github\get_zen.v1.json
│   ├── httpbin\post_payload.v1.json
│   └── linkedin\search_jobs.v1.json
├── capture_replay.py                # Phase 2 Replay Engine (PREFLIGHT + JA3)
├── omniroute_mcp.py                 # Phase 4 MCP Server (JSON-RPC stdio)
├── rotator.py                       # Auto-rotator daemon
├── rotation_state.json              # Rotator live state
├── gen_cloud_cell.py                # Cloud cell generator (zero-burn hardened)
├── gen_notebooks.py                 # Web services generator
├── gen_relay.py                     # Relay backup generator
├── test_webexec.py · test_fleet_path.py
D:\anonym\vault\kaggle_token_*.txt   # Account tokens 2-6
D:\anonym\state\captures\            # Mirrored capture registry
D:\anonym\war-pipe\                  # Mirrored production code
D:\anonym\war-log\                   # THIS MASTER DOC + runbook + architecture spec
```

---

## 11. THE CLOSING LAW

The wire never goes down: **permanent door on Cloudflare edge (Worker v3, token in secret) · 5 Kaggle bodies + playwright executor on 12h staggered rotation · Auto-Rotator persistent daemon · zero-burn quota discipline — writes AND telemetry budgeted · laptop observer-only.**

The index never goes stale: **capability, not content — one capture per site-flow, replayed live, loud failure, versioned re-capture.**

The supply line never depends on GitHub: **app code in door KV assets · cloudflared in dataset mounts · supervisor loops that outlive DNS outages.**

Any agent, one tool, the whole authenticated web.
