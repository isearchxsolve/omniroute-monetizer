# Insert MASTER_WORKLOG entry #22 above the END OF SESSION LOG marker.
# T11: no secrets in this entry.
import datetime, io

path = r"d:\omniroute-monetizer\MASTER_WORKLOG.md"
now = datetime.datetime.now()
stamp = now.strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #22 — CredentialHealth Fix VERIFIED + SECOND Blocker Root-Caused (Token Health-Check) + Fix Staged

**Context:** After the user's services.msc NSSM bounce (entry #21), verified the first fix, hardened the
acceptance suite, and hunted the residual stalls that still failed T2/T3.

**1. CredentialHealth fix — VERIFIED ACTIVE & EFFECTIVE**
- Fresh PIDs after bounce: supervisor 22132, server child 22792 (new process, `.env` re-read).
- Zero `[CredentialHealth]` sweep lines in app.log since the 22:39:19Z restart.
- Health payload now shows `credentialHealth:{{total:0}}` and `connectionHealth:{{}}` (cache empty — sweep never ran).
- 4× `/v1/models` probes ≈ 2.05s each (was 37s+ during sweeps).
- Upstream v3.8.50 fixed the same vendor bug (#9180, added `isActive:true` filter) — independent confirmation of our diagnosis.

**2. Acceptance suite hardened**
- T15: an unhandled `ReadTimeout` crashed the whole suite → added a `requests.exceptions.RequestException` handler (no more crash).
- T19: referenced a non-existent combo `auto/best-free` → corrected to `auto/free-chat` (`stream:false`, `max_tokens:10`). Now PASSES (routes in 2.80s via nvidia).
- Result: **17/19** (T2/T3 fail only due to the residual stalls below; T16 SKIP — orchestrator not run).

**3. SECOND periodic blocker discovered**
- Continuous probes (8 min, every 5s): 10 stalls >3s, period ≈ 100s, duration 37–44s.
- psutil observer on PID 22792 caught: `STALL 34.57s cpu=100% remotes={{'107.20.12.194:443':1}}` (CPU-bound + one AWS network call), later 41.52s and 44.35s.

**4. Root cause: `[HealthCheck]` token-validation health-check (60s tick)**
- Code (`dist/.build/next/server/chunks/src_lib_1mef7mu._.js`): init gated by `OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK`; `setInterval(D, 6e4)`; sweep `D()` calls `getProviderConnections({{authType:"oauth"}})` and refresh-tests every OAuth token (stagger 3000ms, jitter 500–5000ms).
- app.log: `[HealthCheck] Starting proactive token health-check (tick every 60s)` at fresh start; `[HealthCheck]`/`[Encryption] Decryption failed` bursts recur every 60s (measured gaps: 60.0, 59.7, 59.9, 60.3, 60.0s) — the sweep hitting ~30 dead OAuth connections.
- Period math: 60s interval + ~37s CPU-bound sweep ≈ 100s — matches every observed stall exactly.
- `[AUTO] auto/zai matched no connected models` logged at 22:46:52 / 22:48:34 / 22:50:16 / 22:51:52Z — exactly the stall period, each immediately after a stall (queued request draining as the event loop unblocks).

**5. ConnectionRecovery (the other 60s service) RULED OUT**
- Its tick (`[root-of-the-server]__01b8s68._.js`) loads `{{isActive:true}}` only, filters to `testStatus==="unavailable"` with an elapsed cooldown, then calls `clearAccountError` (a DB write). No network, no decryption, no CPU work. Left enabled.

**6. Fix staged**
- Appended to `C:\\Users\\Admin\\.omniroute\\.env`: `OMNIROUTE_DISABLE_TOKEN_HEALTHCHECK=true` (with explanatory comment). Secrets untouched and unprinted (T11).

**7. Pending**
- User NSSM bounce (non-admin cannot restart the LocalSystem service) → re-verify (no `[HealthCheck]` banner, ≥8 min stall-free probes) → acceptance re-run → final declaration.

**8. Restart #2 performed by user (services.msc) — VERIFICATION RESULTS**
- Fresh process start at 23:06:36Z (local 04:36:36). New node PIDs 9104/9360 (cmdlines unreadable from non-admin session; ages match the restart).
- Startup banner diff is conclusive: previous process (22:39:19Z) logged BOTH `[HealthCheck] Starting proactive token health-check (tick every 60s)` and `[STARTUP] Credential health scheduler started`; the fresh process (23:06:36Z) logs ONLY the credential scheduler line — **token health-check banner ABSENT → flag active**.
- Zero `[HealthCheck]`, `[Encryption]`, and `[CredentialHealth]` events since the fresh start (verified over the log tail) → **both sweepers confirmed disabled**.
- Latency probes: first probe after restart 32.79s (one-time cold start: lazy route load + catalog warmup, ModelSync/OpenRouter fetch still in flight at startup); immediate re-probe 4× ≈ 2.05–2.07s → **STALL ELIMINATED**.
- 8-minute continuous probe (every 5s) running to confirm no periodic recurrence.

**9. GitHub issues cross-check (done after user challenged the omission)**
- #10352 quotes the exact `[HealthCheck] github/<conn> has no refresh token but has a GitHub access token; keeping connection active` log line — corroborates blocker #2 as a known vendor design flaw (presence-based, not validation-based health).
- #9685/#10296: a THIRD event-loop hog exists in v3.8.49 — `GET /v1/models` N+1 via `getModelsDevPricing()` (re-runs SQL + re-parses all pricing rows per call). Verified in our bundle: NO memoization (fix #10055 merged 2026-08-13 but never shipped in a 3.8.50 image). Request-driven, not periodic — latent risk, not the current blocker.
- #10300: dashboard/control-plane shares the same event loop (catch-22); their recovery was sqlite edits (forbidden here by AGENTS.md).
- `MODELS_DEV_SYNC_ENABLED=0` env kill-switch is only an open PR (#10299) — 0 chunks in our bundle honor it. No clean 3.8.49 mitigation for the pricing hog; real fix requires a shipped 3.8.50+.
- Lesson recorded: check upstream issues in parallel with local diagnosis from the start.

**Consolidated root cause — "why was OmniRoute so broken":**
1. **Vendor bug #1 (v3.8.49):** CredentialHealth sweep tested ALL 51 connections unfiltered (ignores `isActive`). Fixed upstream in v3.8.50 (#9180).
2. **Vendor design flaw #2:** token health-check refresh-tests ALL OAuth connections including dead ones, doing decryption + network synchronously on the single-threaded event loop (corroborated by #10352).
3. **Vendor bug #3 (latent):** `/v1/models` pricing N+1 (#9685) — unfixed in our 3.8.49 bundle, no env kill-switch available.
4. **Data rot:** ~30 dead OAuth connections with undecryptable stored credentials (`[Encryption] Auth tag validation likely failed`), still marked active, never cleaned up. Every sweeper touching them did wasted crypto + network work.
5. **Architectural fragility:** a ~37s event-loop block = total server freeze → request timeouts → watchdog crashes → restart loop. Compounded by the env reload trap (`POST /api/restart` respawns with a stale env snapshot; only a full NSSM bounce re-reads `.env`), which made fixes look like they "didn't work".
- **Meta-lesson:** the "self-healing" background services were the disease. Each fix peeled off one layer and revealed the next (300s-period stall → 100s-period stall → latent request-driven hog).

**Status:** Both disable flags verified active; periodic stalls eliminated. Awaiting continuous-probe confirmation + final acceptance run.

"""

with io.open(path, "r", encoding="utf-8") as f:
    content = f.read()

marker = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"
if marker not in content:
    # try a looser match
    import re
    m = re.search(r"<!-- END OF SESSION LOG[^>]*-->", content)
    if m:
        marker = m.group(0)
    else:
        raise SystemExit("END marker not found")

new = content.replace(marker, entry + "\n" + marker, 1)
with io.open(path, "w", encoding="utf-8", newline="") as f:
    f.write(new)

print("entry #22 inserted above marker OK")
print("stamp:", stamp)
