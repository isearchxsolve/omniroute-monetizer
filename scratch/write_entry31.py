"""Insert MASTER_WORKLOG entry #31 above the END marker. T11-safe: no secrets."""
import datetime

PATH = "MASTER_WORKLOG.md"
MARKER = "<!-- END OF SESSION LOG — new entries are appended above this marker -->"

stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

entry = f"""
### [{stamp}] #31 — STAGE 1 COMPLETE + DECISIVE FINDING: TTL-clamp hotfix is INERT (dead code); real fix is an API setting
**What:** Completed the clean-slate Stage 1 sandbox validation, then ran a ground-truth investigation that OVERTURNED the hotfix premise. The Zod `.max(6e4)→.max(6e5)` clamp patch does NOT change runtime behavior — it is dead code on both the read and write paths. The real, dramatically simpler fix is to set `modelCatalogCacheTtlMs` high via the settings API (no code patch, no NSSM bounce, no chunk backup needed).

**Stage 1 clean-slate redo (completed):** Killed all ghost/dangling node processes matching `*omniroute-sandbox*`, wiped `d:\\omniroute-sandbox`, fresh `npm install --ignore-scripts` (1185 packages, ~9 min, omniroute 3.8.49, 8019 chunks), re-applied the TTL-clamp hotfix (3 patches + `.bak` backups, verified), recreated `.env` (PORT=20199, isolated DATA_DIR, WS ports offset to 20231/20232 to avoid live collision, INITIAL_PASSWORD bootstrap var, STORAGE_ENCRYPTION_KEY, health-check disables), booted (129 migrations, onboarded), verified isolation (sandbox 20199 vs live 20128 both healthy), login OK.

**The decisive discovery (proof chain):**
1. **Write path is unvalidated.** `PUT /api/settings/cache-config` (handler chunk `_177w922._.js`) uses its OWN inline Zod schema `modelCatalogCacheTtlMs: z.number().positive().optional()` — only `.positive()`, NO `.max()`. Negative control: PUT 600001 (above even the patched 600000 ceiling) → accepted 200 `{{"ok":true}}` and persisted raw to DB via `updateDatabaseSettings({{cache:o}})`.
2. **Read path is unvalidated.** `GET /api/settings/cache-config` reads `(0,n.getDatabaseSettings)().cache ?? {{}}` RAW with NO `.parse()`, then returns `e[r] ?? default`. GET returned `modelCatalogCacheTtlMs: 600001` unclamped — proving the read path never applies the schema.
3. **Runtime consumer uses the same raw read.** The catalog-cache consumer (7 duplicated chunks, e.g. `_0dfofzt._.js`) does `r = Q.CATALOG_CACHE_TTL_MS_DEFAULT; try {{ r = (await getDatabaseSettings()).cache?.modelCatalogCacheTtlMs ?? default }} catch {{}}` then stores cache entries with `expiresAt = Date.now() + cacheTTL`. The patched `.max(6e5)` lives in the MAIN settings schema, which is never `.parse()`d on this path. ⇒ The clamp is dead code.
4. **Empirical proof the runtime honors the raw DB TTL dynamically.** Cache mechanism: `expiresAt = now + TTL`, plus a 30s stale-while-revalidate window. Test: set TTL=5000 → populate (1.119s MISS) → immediate re-request (0.122s HIT) → wait 40s (beyond 5s TTL + 30s stale window) → request = 1.516s SLOW rebuild. The cache expired at exactly the configured 5s. ⇒ The runtime reads and honors the raw DB TTL value per-request, no restart needed.

**Strategy implication (revised plan):** Blocker #3 (60s TTL → synchronous CPU-bound cold rebuilds freeze the server 30–38s every ~94–101s on live, which has 51 connections) does NOT require patching minified production code. The fix is a single authenticated `PUT /api/settings/cache-config` setting `modelCatalogCacheTtlMs` high (e.g. 600000 = 10 min), which reduces rebuild cadence ~10x (freeze every ~10 min instead of every ~94s). No code change, no NSSM bounce, no chunk backup — only a trivial settings backup. The full async-rebuild fix still ships in unreleased v3.8.50; raising the TTL is the best available mitigation until then.

**Files touched:** `scratch/find_getdatabasesettings.py`, `scratch/find_getdbs2.py`, `scratch/find_updatedbs.py`, `scratch/find_ttl_literals.py`, `scratch/find_getdbs3.py`, `scratch/dump_getdbs_body.py`, `scratch/find_getdbs_impl.py`, `scratch/find_diag_headers.py`, `scratch/resolve_h_module.py`, `scratch/find_cacheconfig_handler.py`, `scratch/verify_ttl_fresh_read.py`, `scratch/probe_catalog_headers.py`, `scratch/test_ttl_honored.py`, `scratch/test_ttl_definitive.py` (all new); sandbox `.env` + hotfix re-applied.
**Verification:** GET cache-config returns raw 600001 (unclamped); definitive TTL test shows 5s TTL honored (slow rebuild after 40s). Sandbox TTL restored to 600000. Live untouched (PID 9360, port 20128).
**Status:** ✅ Stage 1 complete with decisive finding. ⏸️ HOLDING before Stage 2/3 — the plan changed from "code patch" to "API setting"; presenting revised plan to user for approval before touching live.

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
print("entry #31 inserted above marker OK")
print("stamp:", stamp)
