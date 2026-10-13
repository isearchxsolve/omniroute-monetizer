# OMNIROUTE FLEET — AGENT INTERNET ARCHITECTURE (CANONICAL)

**Date:** 2026-10-13 · **Status:** Phase 1/2/4 LIVE + Phase 3 verified · Gateway door-side live, kernel registration converging
**This folder is the source of truth for every fleet script.** `C:\kaggle\working\` is the runtime deployment mirror; regenerate it from here with the `gen_*.py` kernels scripts.
Battle history lives in `D:\anonym\war-log\` (mirrored in `docs/`).

---

## 1. THE ONE-PARAGRAPH TRUTH

One permanent Cloudflare Worker door exposes a single tool (`web.execute`) that any AI agent on Earth calls. Simple public fetches execute at the edge (~100ms). Authenticated, multi-step, and browser-rendered targets execute as real HTTP / headless Chromium from a rotating fleet of Kaggle bodies coordinated through the same door. Parag Agarwal's Parallel built a photograph of the web (content, stale, public-only). We built hands (capability, always fresh, behind logins).

## 2. THE PERMANENT DOOR

```
https://omniroute-relay.omniroute-fleet-kd.workers.dev     (never changes)
Worker: omniroute-relay · v3 · token in Worker secret OMNIROUTE_TOKEN (value GOLD24)
KV namespace: LEDGER (2f515e3ac11142f4a0f330dc802ed0a8)
Source: cf-worker/src/worker.js   Redeploy: cd cf-worker && npx wrangler deploy
Secret rotate:    npx wrangler secret put OMNIROUTE_TOKEN   (no redeploy needed)
```

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health?token=` | liveness + version |
| POST/GET | `/say?token=` | ledger write/read (`ledger:{body}`) |
| POST | `/v1/tools/web.execute?token=` | edge (auto) · fleet · playwright queue |
| GET/POST | `/v1/tools/web.result?token=` | job readback / fleet result post (KV TTL 86400s) |
| POST | `/v1/gateway/register?token=` | kernel registers live session (KV TTL 1800s) |
| GET | `/v1/gateway?token=[&service=]` | live session pool |
| ANY | `/v1/gateway/route?token=&service=X&path=` | proxy through to a live session |
| POST/GET | `/v1/assets/{key}?token=` | KV supply line ≤20MB (app code bundles) |

Ledger bodies: `KILO` `OMNIROUTE` `WEBEXEC` `PLAYWRIGHT` `TUNNELDBG` `WXDBG` `WEBEXEC_ERR` `ROTATION` `ROTATION_ERR`.

## 3. EXECUTION PATHS

| Path | Who | When | Latency |
|------|-----|------|---------|
| edge | Worker `fetch()` | public GET/HEAD, no cookies/capture | ~100ms |
| fleet | Kaggle cloud cell (`ledger:WEBEXEC`) | authed wires, multi-step, capture replay | 3-15s |
| playwright | Kaggle headless-Chromium kernel (`ledger:PLAYWRIGHT`) | pure-JS SPAs, DOM extraction, screenshots | 4-30s |

## 4. THE FLEET

| Kernel | Role | Supervisor |
|--------|------|------------|
| `*/omniroute-cloud-cell-cpu-worker` | THE EXECUTOR — subprocess-curl, polls WEBEXEC + OMNIROUTE | — |
| `*/kaggle-fleet-worker-cpu-only` | heavy-work JOB_START/JOB_CHUNK executor | — |
| `*/omniroute-relay` | Kaggle-hosted backup door (quick tunnel) | — |
| `*/oiioii-kaggle-web` | OiiOii Film Kit Studio (app) | supervisor v3 |
| `*/emergentsh-kaggle-web` | EmergentSH NeonBuild (app) | supervisor v3 |
| `isearchxsolve/omniroute-playwright-executor` | Phase 3 headless Chromium | — |

**Accounts:** isearchxsolve (default), n42888 (token_2), kunaldas3104 (token_3), kdas19999 (token_4) — vault `D:\anonym\vault\kaggle_token_*.txt`.
**Cap:** 5 concurrent batch CPU sessions per account. `rotator.py` enforces pre-warm rotation (T-45min), ERROR/UNKNOWN revival, cap fall-through. Run it as a persistent daemon: `python rotator.py` from `C:\kaggle\working`.

## 5. SUPERVISOR v3 (web kernels) — THE IMMORTAL CELL

One notebook cell. NOTHING blocks before telemetry. Order inside the loop:
`door_probe (watchdog)` → `ensure_cloudflared` (dataset mount first, download fallback) → `stage_code` (door KV asset first, git clone fallback) → `ensure_deps_serial` (backend requirements, filtered) → `ensure_shim` (127.0.0.1:8190) → `ensure_server` (uvicorn, cwd=backend) → `ensure_tunnel` (quick tunnel → GitHub publish → door report) → `register_gateway` (every 10 min).

**Hard laws baked in (2026-10-13):**
1. **KV write budget (1,000/day shared):** telemetry on state change only, ≥10-min gap; heartbeat ≤ every 50 min. Burst per-cycle reports burned the whole day's quota once — never again.
2. **DNS watchdog:** 12 consecutive failed `/health` probes (~3 min) → `os._exit(1)` → rotator revives on a fresh account (fresh DNS lottery). Kaggle egress is proxy-based: when DNS dies, NOTHING reaches the door — IP-pin is laptop-only.
3. **Zip discipline:** Python-made zips only (forward slashes); kernel sanitizer normalizes entry paths anyway (Windows `Compress-Archive` backslash entries = silent no-directory extraction).
4. **py3.13:** filter `asyncpg` pins (no 3.13 wheels → build fails → aborts whole `-r` install); install `asyncpg>=0.30`.
5. **Door writes can silently fail:** `/say` returns `ok:true,stored:false` when KV write fails. Treat `stored:false` as failure upstream.

## 6. SESSION-POOL SHIM (the inference gateway consumer contract)

`tools/session_pool_shim.py` runs on `127.0.0.1:8190` inside web kernels. EmergentSH **hard-validates** `OMNIROUTE_BASE_URL == http://127.0.0.1:8190/v1` (rejects everything else by design — see its `nim_client.py`). The shim serves `/v1/models` locally (`session-pool/auto`) and proxies everything else to the door's `/v1`. This IS the "Kaggle inference gateway" consumer surface.

## 7. CAPTURE REGISTRY (Phase 2)

`state/captures/{site}/{flow}.json` — 3 production captures: `github.get_zen.v1`, `httpbin.post_payload.v1`, `linkedin.search_jobs.v1`.
Schema: wire steps + params + fresh_fields (epoch/uuid) + TLS impersonation (curl_cffi) + sentinel liveness probes. Engine: `tools/capture_replay.py`. Doctrine: capability index, not content — one capture per site-flow, replayed live, loud failure, versioned re-capture.

## 8. DEPLOY / OPS

```powershell
# regenerate runtime notebooks from source
python kernels\gen_cloud_cell.py ; python kernels\gen_playwright.py ; python kernels\gen_notebooks.py
# deploy runtime mirror (C:\kaggle\working is the live path)
copy kernels\*.py C:\kaggle\working\
# rotator daemon (persistent)
python C:\kaggle\working\rotator.py
# door redeploy / secret
cd cf-worker ; npx wrangler deploy ; npx wrangler secret put OMNIROUTE_TOKEN
# door asset upload (app supply line)
curl -X POST "https://omniroute-relay.../v1/assets/oioi-zip?token=GOLD24" --data-binary "@oioi.zip"
```

Kernel pushes: `kaggle kernels push -p <notebook-dir>` with the OWNER's token env `KAGGLE_API_TOKEN`. Private datasets are per-account — public dataset `healingsounds/cloudflared-offline` supplies cloudflared to every account.

## 9. KNOWN ENVIRONMENT WAR FACTS (2026-10-13)

1. GitHub releases downloads blocked from Kaggle; git-over-HTTPS flaky. Supply via door KV assets + dataset mounts.
2. Kaggle DNS dies intermittently for hours per session → supervisor + watchdog + rotator converge.
3. Kaggle egress proxy blocks direct-IP HTTPS.
4. Kaggle dataset creation was broken platform-side on 2026-10-13 (uploads OK, datasets never materialize).
5. KV 1,000 writes/day is a shared kill-switch — budget every write.
6. Python 3.13 on Kaggle vs 3.11 on laptop: validate locally first (Baba's law), filter version-pinned wheels.

## 10. FILE MAP

```
fleet/
├── cf-worker/src/worker.js        # THE DOOR v3
├── cf-worker/wrangler.toml
├── kernels/rotator.py             # auto-rotator daemon
├── kernels/gen_cloud_cell.py      # cloud-cell generator
├── kernels/gen_playwright.py      # Phase 3 kernel generator
├── kernels/gen_notebooks.py       # supervisor v3 web-kernel generator (SOURCE OF TRUTH)
├── kernels/gen_relay.py
├── tools/capture_replay.py        # Phase 2 replay engine
├── tools/omniroute_mcp.py         # Phase 4 MCP server (JSON-RPC stdio)
├── tools/session_pool_shim.py     # 8190 consumer endpoint reference
├── tools/test_webexec.py · test_fleet_path.py · verify_fleet.py
├── state/captures/                # Phase 2 registry (3 production captures)
├── runtime/kaggle_notebooks/      # current generated kernels (artifacts)
├── runtime/rotation_state.snapshot.json
├── docs/                          # war-log mirrors
└── ZERO_BURN.md
```

Runtime mirror (live): `C:\kaggle\working\` — same files, plus `rotator.log`, `rotation_state.json`, kernel outputs.
App repos: `D:\god_ai\oioi\oioi` (OiiOii) · `D:\god_ai\emergentsh-standalone-clean` (EmergentSH) — see their `docs/OMNIROUTE_DEPLOYMENT_2026-10-13.md`.
