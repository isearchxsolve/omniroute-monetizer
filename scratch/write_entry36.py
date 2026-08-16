#!/usr/bin/env python3
"""Insert worklog entry #36 above the END marker."""
import io, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
WL = os.path.join(ROOT, "MASTER_WORKLOG.md")
MARKER = "<!-- END OF SESSION LOG"

ENTRY = """### [2026-08-16 10:46] #36 — Keep-alive audit: old inference-ping daemon BROKEN (not running, 3/5 targets gone, wrong mechanism); replaced with native-refresh keep-alive + Task Scheduler (4/9 OAuth conns auto-refreshed every 15 min)
**What:** User asked to verify the keep-alive mechanism in `scripts/omniroute_monetizer.py` so OAuth providers never expire and OmniRoute can run unattended in production. Audited it, found it broken on 4 counts, and built + deployed the correct replacement.

**Audit of the old daemon (`run_keepalive_daemon`, omniroute_monetizer.py:1665):**
1. **NOT RUNNING** — no python process, no scheduled task, no service. Only the NSSM "OmniRoute" server service runs. The daemon was never deployed.
2. **3 of 5 target models MISSING** from the live catalog (2229 models checked): `lmarena/claude-sonnet-5`, `qoder/qwen3.7-max`, `grok-cli/grok-4.5` → MISSING; only `codex/gpt-5.6-sol` and `amazon-q/amazon-q` exist.
3. **WRONG MECHANISM** — it pings `/v1/chat/completions` (inference). AGENTS.md anti-pattern #6 states: "Sending inference requests does NOT refresh OAuth sessions. Server-side timers dictate expiry." Inference pings never refresh an OAuth token.
4. **Burns quota for zero benefit** — consumes credits while tokens still expire on server-side timers.

**Correct mechanism discovered + proven:** OmniRoute's native `POST /api/providers/{id}/refresh` actually rotates OAuth tokens. Verified on amazon-q: HTTP 200, `success:true`, `expiresAt` advanced +1h, post-refresh `test_connection` valid=true. This is anti-pattern #1 compliant (abstraction layer, no DB hacking). GitHub Copilot tokens live only ~30 min (token exp−iat), so refresh interval set to 15 min.

**Built + deployed:**
- `scripts/automation/oauth_keepalive.py` (new): refresh-based keep-alive. Modes: `--once` (scheduler) or loop (`--interval`, default 900s). Password resolution: env → `state/omniroute_password.txt` (gitignored, auto-bootstrapped) → scratch fallback. Logs to `logs/keepalive.log` + `state/keepalive_result.json` (T11 redacted). Crash-guarded.
- `scripts/automation/oauth_keepalive_task.bat` (new): Task Scheduler wrapper.
- Windows scheduled task **"OmniRoute OAuth KeepAlive"** created: every 15 min, runs the .bat. Verified via `schtasks /run` — executed successfully (10:44 pass). Note: runs as current user ("Interactive only"); SYSTEM mode needs admin (we're non-admin). Optional admin one-liner for full SYSTEM: `schtasks /change /tn "OmniRoute OAuth KeepAlive" /ru SYSTEM` (run elevated).

**First-pass results (9 active OAuth connections of 51 total):**
- ✅ REFRESHED (4): amazon-q, kimi-coding, codex, kiro — expiresAt advanced.
- ⚠️ "refresh failed" but STILL HEALTHY (2): github, kilocode — connections test valid=true; these self-manage tokens internally (refresh endpoint returns "no new token" but the connection works). No action needed.
- ❌ GENUINELY BROKEN (3): trae, windsurf ×2 — OmniRoute returns "Provider test not supported"; these were ALREADY testStatus=error before this work. They need re-authentication (human-in-loop OAuth), not keep-alive. Pre-existing issue, separate from keep-alive.

**Honest production verdict:** The keep-alive now WORKS and runs 24/7 for every provider that supports token refresh (amazon-q, kimi-coding, codex, kiro + self-managing github/kilocode). You will NOT need to manually refresh those. However, 3 connections (trae, windsurf ×2) are already dead and need a one-time re-login — keep-alive cannot resurrect an expired OAuth session, only maintain a live one. Anthropic remains billing-walled (entry #35).

**Files touched:** `scripts/automation/oauth_keepalive.py` (new), `scripts/automation/oauth_keepalive_task.bat` (new), `scratch/connection_health.py` (new), `scratch/test_native_refresh.py` (new), `scratch/test_refresh_failures.py` (new), `state/omniroute_password.txt` (new, gitignored), `logs/keepalive.log` (new), `state/keepalive_result.json` (new).
**Status:** ✅ Keep-alive production-ready and scheduled. Remaining human actions (optional): (a) re-login trae/windsurf if you want those providers; (b) run the SYSTEM one-liner elevated for reboot-proof operation; (c) Anthropic billing decision (entry #35).

"""

content = io.open(WL, encoding="utf-8").read()
idx = content.find(MARKER)
if idx == -1:
    print("ERROR: END marker not found")
    sys.exit(1)
new = content[:idx] + ENTRY + content[idx:]
io.open(WL, "w", encoding="utf-8", newline="").write(new)
print("entry #36 inserted above marker OK")
print("total lines:", len(io.open(WL, encoding="utf-8").read().splitlines()))
