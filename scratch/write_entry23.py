"""Insert MASTER_WORKLOG entry #23 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #23 — RETRACTION: Periodic Stalls NOT Eliminated — Continuous Probe Proves ~100s Recurrence Persists (Third Actor: auto-combo pool rebuild)
**What:** 8-minute continuous probe (67 probes, 5s interval) completed after restart #2; result contradicts the "STALL ELIMINATED" claim made in entry #22.
**Why:** Entry #22's conclusion rested on a 4-probe spot check (~2.05s each) that happened to fall between stall windows. The continuous probe was started specifically to catch periodic recurrence — and it did.
**Findings:**
1. **Probe result (terminal, 04:46–04:53 local):** 9 stalls >3s over 480s: 32.84s, 29.13s, 35.53s, 34.43s, 38.19s (plus 4 tail stalls 4.3–6.0s). Period ≈ 100s (04:46:29 → 04:48:03 → 04:49:44 → 04:51:23 → 04:53:07). Same signature as pre-fix stalls.
2. **Both sweepers remain confirmed dead:** zero `[HealthCheck]` / `[CredentialHealth]` / `[Encryption]` events since fresh start 23:06:36Z (entry #22 verification stands). The two disabled flags ARE effective against their targets.
3. **Correlation with app.log:** each stall window contains an `[AUTO] auto/zai matched no connected models; returning an empty pool.` warning followed by a burst of `[MODEL] Treating "nvidia/nemotron-3-super-120b-a12b" as an exact model id` debug lines. Warning timestamps since restart: 23:07:01, 23:14:44, 23:16:24, 23:17:55, 23:19:37, 23:21:15Z → ~100s cadence after warmup.
4. **Code evidence:** the warning originates in `open-sse_services_autoCombo_*.js` — the auto-combo candidate-pool builder. It calls `getCachedProviderConnections({{isActive:true}})` + `({{isActive:false}})` + `getSettings()`, then filters the full model pool per auto-combo family/category/tier. The ~100s cadence indicates a cache-TTL-driven rebuild (no 80–130s `setInterval` exists in the bundle — verified by regex scan), i.e. the pool cache expires and the next `/v1/models` request pays the full synchronous rebuild cost on the event loop.
5. **`auto/zai` is a dead family:** the zai provider has no connected models, so its pool is empty — but the rebuild still walks the full catalog for every auto-combo, which is what blocks the loop ~30–38s.
6. `LocalHealthCheck` (localhost-only, 5s timeout, backoff 30s→5min) and `ConnectionRecovery` (DB-only) re-confirmed NOT the culprit.
**Actions taken:**
- Ran continuous probe to completion; correlated stall timestamps with app.log warnings.
- Scanned all dist chunks for the warning source and for 80–130s intervals (none found → cache-TTL hypothesis).
- RETRACTING entry #22's "stalls eliminated" conclusion. Correct status: the two sweeper fixes are verified, but a THIRD periodic event-loop hog (auto-combo pool rebuild, ~100s cache-TTL cadence) persists.
**Fixes applied:** none yet — candidate mitigations under evaluation: (a) `OMNIROUTE_AUTO_FREE_FALLBACK_TO_FULL_POOL` env (changes empty-pool behavior, may not reduce rebuild cost); (b) remove/deactivate the dead `auto/zai` combo so its rebuild is skipped; (c) check upstream for a fix in shipped 3.8.50+.
**Files touched:** none (investigation only).
**Verification:** probe output + log correlation above.
**Status:** ⚠️ Partial — MONETIZER_READY declaration WITHHELD until third hog is resolved or proven benign for real traffic.

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
print("entry #23 inserted above marker OK")
print("stamp:", stamp)
