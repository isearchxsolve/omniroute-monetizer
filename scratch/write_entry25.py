"""Insert MASTER_WORKLOG entry #25 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #25 — DECISION: Wait for v3.8.50 (no unsafe local patch) — Second Opinion (Stack Overflow) Confirms GitHub Fix Approach + TTL Hotfix Retracted
**What:** Completed the second-opinion cross-check requested by the user (Stack Overflow as the discipline-standard reference), finalized the blocker #3 decision, and set up a release watcher.
**Second opinion (Stack Overflow, via official Stack Exchange API):**
1. **Diagnosis confirmed:** SO #47032981 (accepted) — CPU-bound code inside async/await "will block the entire Node.js process". Matches our blocker #3 exactly (pure-CPU catalog rebuild, zero network calls, freezes all routes 30–38s).
2. **Fix approach confirmed:** SO #60259141 (accepted, score 12) — stale-while-revalidate = "respond immediately from the cache, then refresh the cache in the background for the next time"; appropriate when data need not be the very latest. Model catalog qualifies (changes hourly/daily, not per-second). This is verbatim what PR #8728 implements.
3. **TTL-raise rejected by consensus:** SO #75590731 — "cache invalidation is hard"; longer TTL without reliable invalidation widens the stale-data window. #8697 documents the exact gap: `replaceSyncedAvailableModelsForConnection`/`removeSyncedAvailableModel` write the DB without `invalidateDbCache()`, so a 600s TTL would hide newly-synced models for up to 10 minutes. Maintainers deliberately kept the 60s cap and fixed the blocking behavior instead.
**Decisive local evidence (this session):**
- `scratch/find_rebuild_trigger.py` over app.log: every `[AUTO] auto/zai` warning burst is preceded ~31s earlier by a chat request — rebuilds are REQUEST-DRIVEN after TTL expiry, not background timers. 178 warnings / 126 bursts confirmed.
- `scratch/inspect_catalog_cache.py` + `find_cache_expiry_logic.py`: no simple `now-ts<ttl` expiry pattern in the 8019 chunks; TTL is consumed via the version-keyed memo architecture described in #8697.
**RETRACTION:** the earlier "patch `.max(6e4)` → `.max(6e5)`" hotfix proposal is WITHDRAWN as unsafe (invalidation gap above) and insufficient (makes stalls rarer, not non-blocking). The correct fix is SWR + memoization, which cannot be safely backported into minified webpack chunks.
**DECISION (user-approved, final):** Do NOT patch 3.8.49. Wait for v3.8.50 to publish to npm (fix merged: PR #8728 SWR + #8987 memoization + #9199 responsiveness, all in `release/v3.8.50`, branch actively committed). Watcher installed to alert on publication. Blockers #1/#2 remain disabled via .env flags (verified dead). Residual blocker #3 accepted on 3.8.49 until upgrade.
**Actions taken:**
- Cross-checked diagnosis/fix/rejected-alternative against Stack Overflow accepted answers (3 questions).
- Ran app.log trigger diagnostic (request-driven rebuilds confirmed).
- Retracted TTL hotfix; recorded rationale.
- Created `scratch/watch_omniroute_release.py` (npm dist-tags poller for 3.8.50).
**Files touched:** `scratch/inspect_catalog_cache.py`, `scratch/find_cache_expiry_logic.py`, `scratch/find_ttl_consumption.py`, `scratch/find_rebuild_trigger.py`, `scratch/watch_omniroute_release.py` (new).
**Verification:** SO answer bodies retrieved via api.stackexchange.com; app.log burst analysis output above.
**Status:** ⚠️ MONETIZER_BLOCKED on upstream release v3.8.50 — all locally-fixable blockers resolved & verified; blocker #3 requires the shipped SWR fix.

"""

lines = open(PATH, encoding="utf-8", errors="replace").read().splitlines(keepends=True)
out = []
inserted = False
for ln in lines:
    if MARKER in ln and not inserted:
        out.append(entry)
        inserted = True
    out.append(ln)
assert inserted, "marker not found"
open(PATH, "w", encoding="utf-8", newline="").write("".join(out))
print("entry #25 inserted above marker OK")
print("stamp:", stamp)
